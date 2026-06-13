"""Gemini CLI provider（subprocess 调用 ``gemini`` 命令）。"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import Dict, List, Tuple

from agent_platform.config.settings import Settings
from agent_platform.domain.models import LlmError, LlmTokens, LlmTransportError, Mode, Recap
from agent_platform.infra.llm.parse import parse_and_validate
from agent_platform.infra.llm.providers._cli_shared import (
    _run_cli_subprocess,
    inject_prefetch,
)

logger = logging.getLogger("agent_platform.infra.llm.providers.gemini_cli")


class GeminiCliProvider:
    name = "gemini-cli"

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
        base_cmd = settings.gemini_cli_cmd.strip().split()
        if not base_cmd:
            raise LlmError("gemini-cli 命令为空，请设置 RECAP_GEMINI_CLI_CMD")

        msgs = inject_prefetch(messages, settings, db_path, date)

        prompt_parts: List[str] = []
        for msg in msgs:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"[System]\n{content}")
            else:
                prompt_parts.append(content)
        prompt = "\n\n".join(prompt_parts)

        env = os.environ.copy()
        if settings.gemini_api_key:
            env["GEMINI_API_KEY"] = settings.gemini_api_key

        cmd = base_cmd + ["-p", prompt]

        stdout_lines = _run_cli_subprocess(
            cmd,
            settings.gemini_timeout_s,
            "gemini-cli",
            logger,
            stderr=subprocess.PIPE,
            env=env,
        )

        raw = "".join(stdout_lines).strip()
        if not raw:
            raise LlmTransportError("gemini-cli 无输出")

        recap = parse_and_validate(raw, mode)
        return recap, LlmTokens()
