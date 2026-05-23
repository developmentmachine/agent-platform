"""A股日终复盘 / 次日策略智能体"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any

import uvicorn

from agent_platform.agents.stock_recap.memory.manager import (
    check_and_run_evolution,
    get_prompt_version,
    load_evolution_guidance,
    load_recent_memory,
)
from agent_platform.adapters.cli.repl import run_repl
from agent_platform.agents.stock_recap.use_case import _try_run_backtest, generate_once
from agent_platform.config.settings import Settings
from agent_platform.core.domain.models import GenerateRequest
from agent_platform.agents.stock_recap.data.collector import collect_snapshot
from agent_platform.agents.stock_recap.data.features import build_features
from agent_platform.infra.llm.backends import llm_backend_effective, model_effective
from agent_platform.agents.stock_recap.llm.prompts import build_messages
from agent_platform.infra.persistence.db import load_feedback_summary, load_history
from agent_platform.infra.push.wechat import test_push
from agent_platform.adapters.scheduler.jobs import start_scheduler


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def register_subparser(sub: argparse.ArgumentParser) -> None:
    """向平台分发器注册 stock-recap 的所有参数。"""
    sub.formatter_class = argparse.RawDescriptionHelpFormatter
    sub.description = "A 股日终复盘 / 次日策略（默认进入交互模式）"
    sub.epilog = """
示例:
  # 交互模式（默认）
  agent-platform stock-recap
  agent-platform stock-recap --provider mock

  # 脚本单轮生成后退出
  agent-platform stock-recap --once --mode daily --provider mock

  # 启动 API 服务（含调度器）
  RECAP_SCHEDULER_ENABLED=true agent-platform stock-recap --serve

  # 一次性管理命令（仍立即执行后退出）
  agent-platform stock-recap --evolve
  agent-platform stock-recap --history
"""

    action_group = sub.add_mutually_exclusive_group()
    action_group.add_argument("--serve", action="store_true", help="启动 API 服务（含调度器）")
    action_group.add_argument("--dry-run", action="store_true", help="仅打印 LLM payload，不调用")
    action_group.add_argument("--evolve", action="store_true", help="手动触发进化分析")
    action_group.add_argument("--backtest", action="store_true", help="手动回测昨日策略")
    action_group.add_argument("--push-test", action="store_true", help="测试企业微信推送配置")
    action_group.add_argument("--history", action="store_true", help="查看最近运行历史")

    sub.add_argument("--mode", choices=["daily", "strategy"], default="daily")
    sub.add_argument(
        "--provider",
        type=str,
        default="live",
        metavar="ID",
        help="行情采集源：mock / live / akshare，或已注册的自定义 id",
    )
    sub.add_argument("--date", type=str, default=None, help="YYYY-MM-DD，默认今天")
    sub.add_argument("--no-llm", action="store_true", help="不调用 LLM，仅采集+落库")
    sub.add_argument(
        "--model",
        type=str,
        default=None,
        help="模型表达：openai:<m> / ollama:<m> / cursor-cli / gemini-cli",
    )
    sub.add_argument("--skip-trading-check", action="store_true", help="跳过交易日检查")
    sub.add_argument(
        "--output-dir", type=str, default=None, help="输出目录（默认 RECAP_OUTPUT_DIR 或当前目录）"
    )
    sub.add_argument("--no-write-files", action="store_true", help="不写文件，仅 stdout")

    sub.add_argument("--ollama-base-url", type=str, default=None)
    sub.add_argument(
        "--cursor-cli-cmd",
        type=str,
        default=None,
        help="Cursor CLI 启动命令及参数前缀（官方为 agent），覆盖 RECAP_CURSOR_CLI_CMD",
    )
    sub.add_argument("--cursor-agent-cmd", type=str, default=None, help=argparse.SUPPRESS)
    sub.add_argument("--cursor-timeout-s", type=int, default=None)

    sub.add_argument("--host", type=str, default="127.0.0.1")
    sub.add_argument("--port", type=int, default=8000)

    sub.add_argument("--limit", type=int, default=10, help="历史记录数量")
    sub.add_argument(
        "--once",
        action="store_true",
        help="单轮模式：按当前参数生成一次报告后退出（不进入交互 REPL）",
    )


def run(
    args: argparse.Namespace,
    settings: Settings,
    parser: argparse.ArgumentParser,
) -> int:
    """执行 stock-recap agent，返回 exit code。"""
    from agent_platform.agents.stock_recap.data.collector import list_data_provider_ids

    _pid = (args.provider or "").strip().lower()
    _allowed = set(list_data_provider_ids())
    if _pid not in _allowed:
        parser.error(f"未知 --provider {args.provider!r}；可用: {', '.join(sorted(_allowed))}")
    args.provider = _pid

    if args.ollama_base_url:
        settings.ollama_base_url = args.ollama_base_url
    if args.cursor_cli_cmd:
        settings.cursor_cli_cmd = args.cursor_cli_cmd
    elif args.cursor_agent_cmd:
        settings.cursor_cli_cmd = args.cursor_agent_cmd
    if args.cursor_timeout_s is not None:
        settings.cursor_timeout_s = int(args.cursor_timeout_s)
    if args.output_dir:
        settings.output_dir = args.output_dir

    logger = logging.getLogger("agent_platform")

    if args.serve:
        return _cmd_serve(settings, logger, args)
    if args.push_test:
        return _cmd_push_test(settings, logger)
    if args.evolve:
        return _cmd_evolve(settings, logger)
    if args.backtest:
        return _cmd_backtest(settings, logger, args)
    if args.history:
        return _cmd_history(settings, logger, args)
    if args.once or args.dry_run:
        return _cmd_generate(settings, logger, args)
    return _cmd_interactive(settings, logger, args, parser)


_RECAP_HELP = """
命令:
  run [daily|strategy]  生成复盘/策略（默认用当前 mode）
  daily / strategy      同 run daily / run strategy
  dry-run               打印 LLM payload，不调用
  history [N]           最近 N 条运行记录（默认 10）
  evolve                手动触发进化分析
  backtest [DATE]       回测（日期 YYYY-MM-DD，默认今天）
  push-test             测试企业微信推送
  set mode daily|strategy
  set provider <id>     mock / live / akshare 等
  set model <spec>      如 openai:gpt-4.1-mini
  set date YYYY-MM-DD | clear date
  status                显示当前参数
  help                  本帮助
  quit / exit           退出
"""


def _cmd_interactive(
    settings: Settings,
    logger: logging.Logger,
    args: argparse.Namespace,
    _parser: argparse.ArgumentParser,
) -> int:
    from agent_platform.agents.stock_recap.data.collector import list_data_provider_ids

    allowed = set(list_data_provider_ids())

    def on_line(line: str) -> bool:
        parts = line.split()
        if not parts:
            return True
        cmd = parts[0].lower()

        if cmd in {"/quit", "quit", "/exit", "exit"}:
            return False
        if cmd in {"/help", "help"}:
            print(_RECAP_HELP)
            return True
        if cmd == "status":
            print(
                _stable_json(
                    {
                        "mode": args.mode,
                        "provider": args.provider,
                        "model": args.model,
                        "date": args.date,
                        "no_llm": args.no_llm,
                        "skip_trading_check": args.skip_trading_check,
                        "output_dir": args.output_dir or settings.output_dir,
                    }
                )
            )
            return True
        if cmd == "set" and len(parts) >= 3 and parts[1] == "mode":
            if parts[2] not in ("daily", "strategy"):
                print("mode 须为 daily 或 strategy")
                return True
            args.mode = parts[2]
            print(f"(mode = {args.mode})")
            return True
        if cmd == "set" and len(parts) >= 3 and parts[1] == "provider":
            pid = parts[2].strip().lower()
            if pid not in allowed:
                print(f"未知 provider；可用: {', '.join(sorted(allowed))}")
                return True
            args.provider = pid
            print(f"(provider = {args.provider})")
            return True
        if cmd == "set" and len(parts) >= 3 and parts[1] == "model":
            args.model = parts[2]
            print(f"(model = {args.model})")
            return True
        if cmd == "set" and len(parts) >= 3 and parts[1] == "date":
            if parts[2].lower() == "clear":
                args.date = None
                print("(date = 今天)")
            else:
                args.date = parts[2]
                print(f"(date = {args.date})")
            return True
        if cmd == "history":
            if len(parts) >= 2 and parts[1].isdigit():
                args.limit = int(parts[1])
            _cmd_history(settings, logger, args)
            return True
        if cmd == "evolve":
            _cmd_evolve(settings, logger)
            return True
        if cmd == "backtest":
            if len(parts) >= 2:
                args.date = parts[1]
            _cmd_backtest(settings, logger, args)
            return True
        if cmd == "push-test":
            _cmd_push_test(settings, logger)
            return True
        if cmd == "dry-run":
            args.dry_run = True
            code = _cmd_generate(settings, logger, args)
            args.dry_run = False
            return code == 0
        if cmd in {"run", "daily", "strategy"}:
            if cmd in ("daily", "strategy"):
                args.mode = cmd
            elif len(parts) >= 2 and parts[1] in ("daily", "strategy"):
                args.mode = parts[1]
            print(f"\n--- 生成 {args.mode} ({args.provider}) ---\n")
            code = _cmd_generate(settings, logger, args)
            print()
            return code == 0

        print(f"未知命令: {parts[0]}  (输入 help 查看)")
        return True

    banner = (
        "A 股复盘智能体 · 交互模式\n"
        f"当前: mode={args.mode} provider={args.provider} "
        f"model={args.model or '(默认)'}"
    )
    return run_repl(banner=banner, prompt="recap> ", on_line=on_line)


# ─── 子命令实现 ────────────────────────────────────────────────────────────────


def _cmd_serve(settings: Settings, logger: logging.Logger, args: argparse.Namespace) -> int:
    from agent_platform.adapters.http.api.routes import app

    scheduler = None
    if settings.scheduler_enabled:
        scheduler = start_scheduler(settings)
        logger.info(_stable_json({"event": "scheduler_enabled"}))

    logger.info(_stable_json({"event": "server_start", "host": args.host, "port": args.port}))
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level=settings.log_level.lower())
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
    return 0


def _cmd_push_test(settings: Settings, logger: logging.Logger) -> int:
    if not settings.wxwork_webhook_url:
        print("错误：未配置 RECAP_WXWORK_WEBHOOK_URL", file=sys.stderr)
        return 1
    ok = test_push(settings.wxwork_webhook_url)
    if ok:
        print("企业微信推送测试成功")
        return 0
    else:
        print("企业微信推送测试失败，请检查 Webhook URL", file=sys.stderr)
        return 1


def _cmd_evolve(settings: Settings, logger: logging.Logger) -> int:
    print("正在执行进化分析...")
    new_version = check_and_run_evolution(settings.db_path, settings=settings, force=True)
    if new_version:
        print(f"进化完成，新版本：{new_version}")
    else:
        print("进化分析完成（无版本升级）")
    return 0


def _cmd_backtest(
    settings: Settings, logger: logging.Logger, args: argparse.Namespace
) -> int:
    today = args.date or _today_str()
    print(f"正在回测昨日策略（相对于 {today}）...")
    _try_run_backtest(settings.db_path, today)
    print("回测完成，查看数据库或使用 --history 查看结果")
    return 0


def _cmd_history(
    settings: Settings, logger: logging.Logger, args: argparse.Namespace
) -> int:
    items = load_history(settings.db_path, limit=args.limit)
    print(f"\n最近 {len(items)} 条运行记录：\n")
    for item in items:
        status = "✓" if item["error"] is None else "✗"
        print(
            f"  {status} [{item['date']}] {item['mode']} | {item['provider']} | "
            f"{item['latency_ms']}ms | v{item['prompt_version']} | {item['created_at']}"
        )
        if item["error"]:
            print(f"    错误：{item['error'][:80]}")
    return 0


def _cmd_generate(
    settings: Settings, logger: logging.Logger, args: argparse.Namespace
) -> int:
    req = GenerateRequest(
        mode=args.mode,
        provider=args.provider,
        date=args.date,
        force_llm=not args.no_llm,
        model=args.model,
        skip_trading_check=args.skip_trading_check,
    )

    if args.dry_run:
        snapshot = collect_snapshot(
            req.provider, req.date, skip_trading_check=req.skip_trading_check
        )
        features = build_features(snapshot)
        memory = load_recent_memory(settings.db_path, snapshot.date, req.mode)
        prompt_version = get_prompt_version(settings.db_path)
        evolution_guidance = load_evolution_guidance(settings.db_path)
        feedback_summary = load_feedback_summary(settings.db_path)
        messages = build_messages(
            mode=req.mode,
            snapshot=snapshot,
            features=features,
            memory=memory,
            prompt_version=prompt_version,
            evolution_guidance=evolution_guidance,
            feedback_summary=feedback_summary,
            skill_id_override=settings.skill_id_override,
        )
        print(
            _stable_json(
                {
                    "llm_backend": llm_backend_effective(req.model, settings),
                    "model": model_effective(settings, req.model),
                    "messages": messages,
                }
            )
        )
        return 0

    resp = generate_once(req, settings)

    if resp.recap is None:
        if args.no_llm:
            print(_stable_json(resp.model_dump()))
            return 0
        logger.error(_stable_json({"event": "generate_failed", "request_id": resp.request_id}))
        print(_stable_json(resp.model_dump()), file=sys.stderr)
        return 2

    print(resp.rendered_markdown or _stable_json(resp.model_dump()))

    if not args.no_write_files:
        output_dir = args.output_dir or settings.output_dir
        os.makedirs(output_dir, exist_ok=True)
        base = f"recap_{resp.snapshot.date}_{req.mode}"
        md_path = os.path.join(output_dir, base + ".md")
        wechat_path = os.path.join(output_dir, base + "_wechat.txt")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(resp.rendered_markdown or "")
        if resp.rendered_wechat_text:
            with open(wechat_path, "w", encoding="utf-8") as f:
                f.write(resp.rendered_wechat_text)

        logger.info(_stable_json({"event": "files_written", "md": md_path, "wechat": wechat_path}))

    if resp.push_result is not None:
        status = "成功" if resp.push_result else "失败"
        logger.info(_stable_json({"event": "push_result", "status": status}))

    return 0
