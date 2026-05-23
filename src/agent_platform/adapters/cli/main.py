"""Agent Platform CLI 入口 — W6 起按 ``AgentRegistry`` 自动发现子命令。

用法：
  agent_platform <agent-id> [agent-specific args]
  agent_platform --mcp-tools
  agent_platform --list-agents

新增 agent 时：在 ``agents/<id>/manifest.py`` 中声明
``cli_subparser_factory`` 与 ``cli_run_handler``，本 dispatcher 自动挂载，
不再需要修改任何平台文件。
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Dict

from agent_platform.config.settings import get_settings
from agent_platform.infra.persistence.db import init_db


def _setup_logger(level: str) -> logging.Logger:
    from agent_platform.runtime.observability.logging_setup import setup_structured_logging

    setup_structured_logging(
        level=getattr(logging, level.upper(), logging.INFO),
        stream=sys.stderr,
    )
    return logging.getLogger("agent_platform")


def _load_registry():
    """触发 builtin agent 注册 + entry_points 发现。"""
    # builtin agent — 通过 runtime.create_runtime() 同步触发 register；
    # 这里只需要 import manifest 即可（manifest 不自注册，需手动调 register）。
    from agent_platform.agents.stock_recap import manifest as stock_recap_manifest
    from agent_platform.core.registry.agent_registry import (
        discover_agents,
        get_default_registry,
    )

    reg = get_default_registry()
    if not reg.has(stock_recap_manifest.AGENT_ID):
        stock_recap_manifest.register(reg)
    discover_agents(reg)
    return reg


def cli_main() -> int:
    parser = argparse.ArgumentParser(
        prog="agent_platform",
        description="Agent Platform — 多智能体运行平台",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mcp-tools",
        action="store_true",
        help="启动 MCP stdio 工具服务（与进程内 function calling 语义一致）",
    )
    parser.add_argument(
        "--list-agents",
        action="store_true",
        help="列出所有已注册 agent（来自内置 + entry_points）",
    )

    registry = _load_registry()

    subparsers = parser.add_subparsers(dest="agent", metavar="AGENT")
    subparser_map: Dict[str, argparse.ArgumentParser] = {}
    for defn in registry.list():
        if defn.cli_subparser_factory is None or defn.cli_run_handler is None:
            continue
        sub = subparsers.add_parser(defn.id, help=defn.cli_help or defn.display_name)
        defn.cli_subparser_factory(sub)
        subparser_map[defn.id] = sub

    args = parser.parse_args()

    if args.list_agents:
        for defn in registry.list():
            caps = ",".join(c.value for c in defn.capabilities)
            print(f"{defn.id:<24} [{caps}]  {defn.display_name}")
        return 0

    settings = get_settings()

    if args.mcp_tools:
        from agent_platform.adapters.mcp_stdio.main import run_mcp_stdio
        from agent_platform.runtime.observability.tracing import configure_tracing

        configure_tracing(settings)
        init_db(settings.db_path)
        run_mcp_stdio()
        return 0

    if not args.agent:
        parser.print_help()
        return 1

    _setup_logger(settings.log_level)
    from agent_platform.runtime.observability.tracing import configure_tracing

    configure_tracing(settings)
    init_db(settings.db_path)

    defn = registry.get(args.agent)
    assert defn.cli_run_handler is not None
    return defn.cli_run_handler(args, settings, subparser_map[args.agent])
