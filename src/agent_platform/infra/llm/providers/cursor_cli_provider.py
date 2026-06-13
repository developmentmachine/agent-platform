"""Cursor CLI provider（subprocess 调用官方 ``agent`` 命令，stream-json）。"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Dict, List, Optional, Tuple

from agent_platform.config.settings import Settings
from agent_platform.domain.models import LlmError, LlmTokens, LlmTransportError, Mode, Recap
from agent_platform.infra.llm.parse import _stable_json, parse_and_validate
from agent_platform.infra.llm.providers._cli_shared import (
    _run_cli_subprocess,
    inject_prefetch,
)

logger = logging.getLogger("agent_platform.infra.llm.providers.cursor_cli")


class CursorCliProvider:
    name = "cursor-cli"

    def call(
        self,
        settings: Settings,
        mode: Mode,
        messages: List[Dict[str, str]],
        *,
        model: str,
        db_path: str,
        date: str,
    ) -> Tuple[Recap, LlmTokens]:
        base_cmd = settings.cursor_cli_cmd.strip().split()
        if not base_cmd:
            raise LlmError(
                "cursor-cli 命令为空，请设置 RECAP_CURSOR_CLI_CMD（或兼容项 RECAP_CURSOR_AGENT_CMD）"
            )

        msgs = inject_prefetch(messages, settings, db_path, date)
        prompt = _stable_json({"messages": msgs})
        cmd = (
            base_cmd
            + [
                "--print",
                "--output-format",
                "stream-json",
                "--stream-partial-output",
                "--trust",
                "--force",
                "--workspace",
                os.getcwd(),
            ]
            + [prompt]
        )

        final_result_text: Optional[str] = None
        assistant_text_parts: List[str] = []

        def _parse_line(line: str) -> None:
            nonlocal final_result_text
            try:
                evt = json.loads(line)
                if isinstance(evt, dict):
                    if evt.get("type") == "result" and isinstance(evt.get("result"), str):
                        final_result_text = evt["result"]
                    if evt.get("type") == "assistant":
                        msg = evt.get("message")
                        if isinstance(msg, dict):
                            for c in msg.get("content") or []:
                                if isinstance(c, dict) and c.get("type") == "text":
                                    assistant_text_parts.append(c.get("text", ""))
            except Exception:
                pass

        stdout_lines = _run_cli_subprocess(
            cmd,
            settings.cursor_timeout_s,
            "cursor-cli",
            logger,
            stderr=subprocess.STDOUT,
            line_callback=_parse_line,
        )

        raw = final_result_text or "".join(assistant_text_parts) or "".join(stdout_lines)
        if not raw.strip():
            raise LlmTransportError("cursor-cli 无输出")

        recap = parse_and_validate(raw.strip(), mode)
        return recap, LlmTokens()
