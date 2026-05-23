"""CLI：``agent_platform hsk30-tutor chat``。"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from agent_platform.agents.hsk30_tutor.models import TutorChatRequest
from agent_platform.config.settings import Settings
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.runtime.factory import create_runtime


def register_subparser(sub: argparse.ArgumentParser) -> None:
    chat = sub.add_subparsers(dest="hsk30_cmd", required=True)
    p = chat.add_parser("chat", help="单轮陪练对话")
    p.add_argument("--message", "-m", required=True, help="用户输入")
    p.add_argument("--level", type=int, default=1, choices=range(1, 10), help="HSK 3.0 等级 1–9")
    p.add_argument(
        "--locale",
        choices=("zh", "en", "both"),
        default="both",
        help="讲解语言",
    )
    p.add_argument("--json", action="store_true", help="输出 JSON")


def run(args: Any, settings: Settings, parser: argparse.ArgumentParser) -> int:
    if args.hsk30_cmd != "chat":
        parser.print_help()
        return 1

    req = TutorChatRequest(
        message=args.message,
        level=args.level,
        explain_locale=args.locale,
    )
    runtime = create_runtime(settings)
    principal = PrincipalContext.anonymous(source="cli")
    envelope = runtime.run(
        agent_id="hsk30-tutor",
        payload=req.model_dump(),
        principal=principal,
    )
    if args.json:
        print(json.dumps(envelope.payload, ensure_ascii=False, indent=2))
    else:
        print(envelope.payload.get("reply", ""))
        note = envelope.payload.get("note")
        if note:
            print(f"\n[{note}]", file=sys.stderr)
    return 0
