"""CLI：``agent-platform hsk30-tutor`` 进入交互陪练；``-m`` / ``--once`` 保留脚本单轮。"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, List

from agent_platform.adapters.cli.repl import run_repl
from agent_platform.agents.hsk30_tutor.models import ChatTurn, TutorChatRequest
from agent_platform.agents.hsk30_tutor.use_case import chat_turn
from agent_platform.config.settings import Settings
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.run_context import RunContext
from agent_platform.runtime.factory import create_runtime

_HELP = """
命令（以 / 开头）：
  /help              显示本帮助
  /level <1-9>       设置 HSK 3.0 目标等级
  /locale zh|en|both 设置讲解语言
  /clear             清空对话历史
  /quit, /exit       退出

直接输入中文或问题即可开始陪练。
"""


def register_subparser(sub: argparse.ArgumentParser) -> None:
    sub.formatter_class = argparse.RawDescriptionHelpFormatter
    sub.description = "HSK 3.0 对话陪练（默认交互模式）"
    sub.epilog = """
示例:
  agent-platform hsk30-tutor
  agent-platform hsk30-tutor --level 2
  agent-platform hsk30-tutor -m "请纠正我的句子" --once
"""
    sub.add_argument(
        "--message",
        "-m",
        type=str,
        default=None,
        help="单轮模式：只发送一条消息后退出（需配合 --once）",
    )
    sub.add_argument("--once", action="store_true", help="单轮模式，不进入交互 REPL")
    sub.add_argument("--level", type=int, default=1, choices=range(1, 10), help="HSK 3.0 等级 1–9")
    sub.add_argument(
        "--locale",
        choices=("zh", "en", "both"),
        default="both",
        help="讲解语言",
    )
    sub.add_argument("--json", action="store_true", help="单轮模式下输出 JSON")


def _print_reply(payload: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(payload.get("reply", ""))
    note = payload.get("note")
    if note:
        print(f"\n[{note}]", file=sys.stderr)


def _turn(
    message: str,
    *,
    history: List[ChatTurn],
    level: int,
    locale: str,
    settings: Settings,
    use_runtime: bool,
) -> tuple[dict, List[ChatTurn]]:
    req = TutorChatRequest(
        message=message,
        level=level,
        history=list(history),
        explain_locale=locale,  # type: ignore[arg-type]
    )
    if use_runtime:
        runtime = create_runtime(settings)
        principal = PrincipalContext.anonymous(source="cli")
        envelope = runtime.run(
            agent_id="hsk30-tutor",
            payload=req.model_dump(),
            principal=principal,
        )
        payload = envelope.payload
    else:
        payload = chat_turn(req, settings, ctx=RunContext.new()).model_dump()

    history.append(ChatTurn(role="user", content=message))
    history.append(ChatTurn(role="assistant", content=payload.get("reply", "")))
    return payload, history


def _run_interactive(
    settings: Settings,
    *,
    level: int,
    locale: str,
    as_json: bool,
) -> int:
    history: List[ChatTurn] = []
    state = {"level": level, "locale": locale}

    def on_line(line: str) -> bool:
        low = line.lower()
        if low in {"/quit", "/exit", "quit", "exit"}:
            return False
        if low in {"/help", "help"}:
            print(_HELP)
            return True
        if low == "/clear":
            history.clear()
            print("(对话历史已清空)")
            return True
        if low.startswith("/level"):
            parts = line.split()
            if len(parts) != 2 or not parts[1].isdigit():
                print("用法: /level <1-9>")
                return True
            n = int(parts[1])
            if not 1 <= n <= 9:
                print("等级须在 1–9")
                return True
            state["level"] = n
            print(f"(当前等级: HSK 3.0 Level {n})")
            return True
        if low.startswith("/locale"):
            parts = line.split()
            if len(parts) != 2 or parts[1] not in ("zh", "en", "both"):
                print("用法: /locale zh|en|both")
                return True
            state["locale"] = parts[1]
            print(f"(讲解语言: {parts[1]})")
            return True

        payload, _ = _turn(
            line,
            history=history,
            level=state["level"],
            locale=state["locale"],
            settings=settings,
            use_runtime=True,
        )
        print()
        _print_reply(payload, as_json=as_json)
        print()
        return True

    banner = (
        f"HSK 3.0 中文陪练 · 交互模式\n"
        f"当前等级: Level {state['level']} · 讲解: {state['locale']}"
    )
    return run_repl(banner=banner, prompt="你> ", on_line=on_line)


def run(args: Any, settings: Settings, parser: argparse.ArgumentParser) -> int:
    if args.once or args.message:
        if not args.message:
            parser.error("单轮模式请提供 --message / -m，或去掉 --once 进入交互模式")
        payload, _ = _turn(
            args.message,
            history=[],
            level=args.level,
            locale=args.locale,
            settings=settings,
            use_runtime=True,
        )
        _print_reply(payload, as_json=args.json)
        return 0

    return _run_interactive(
        settings,
        level=args.level,
        locale=args.locale,
        as_json=args.json,
    )
