"""Cursor/Gemini CLI 共享工具：预执行工具结果注入 prompt + subprocess 轮询。"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from typing import Callable, Dict, List, Optional

from agent_platform.config.settings import Settings
from agent_platform.domain.models import LlmTransportError
from agent_platform.infra.llm.parse import _stable_json


def inject_prefetch(
    messages: List[Dict[str, str]],
    settings: Settings,
    db_path: str,
    date: str,
) -> List[Dict[str, str]]:
    """为不支持 function-calling 的后端预执行工具并注入 prompt。

    仅当总开关 + 至少一个子工具开关为 True 时才真正注入；与 function-calling
    路径保持可见性一致，避免「flag 关了但 prefetch 仍在跑」。
    """
    from agent_platform.infra.tools.runner import RecapToolRunner

    runner = RecapToolRunner(settings)
    if not runner.enabled_tool_names():
        return messages
    context = runner.prefetch_for_prompt(date, db_path)
    if not context:
        return messages
    injected = list(messages)
    injected.insert(
        1,
        {
            "role": "user",
            "content": f"【工具预执行结果，请结合以下实时数据进行分析】\n\n{context}",
        },
    )
    return injected


def _run_cli_subprocess(
    cmd: List[str],
    timeout_s: float,
    name: str,
    logger: logging.Logger,
    *,
    stderr: int = subprocess.STDOUT,
    env: Optional[Dict[str, str]] = None,
    line_callback: Optional[Callable[[str], None]] = None,
) -> List[str]:
    """Run a CLI subprocess with timeout + polling + optional per-line callback.

    Returns the collected stdout lines on success.
    Raises ``LlmTransportError`` on launch failure, timeout, or non-zero exit.
    """
    t0 = time.time()
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=stderr, text=True,
            env=env,
        )
    except Exception as e:
        raise LlmTransportError(f"{name} 启动失败: {e}") from e

    stdout_lines: List[str] = []
    last_log = 0.0

    while True:
        now = time.time()
        if now - last_log >= 5:
            last_log = now
            logger.info(_stable_json({"event": f"{name}_running", "elapsed_s": int(now - t0)}))

        if proc.poll() is not None:
            break

        if now - t0 > timeout_s:
            try:
                proc.kill()
            except Exception:
                pass
            raise LlmTransportError(f"{name} 超时（>{timeout_s}s）")

        got = False
        if proc.stdout:
            line = proc.stdout.readline()
            if line:
                got = True
                stdout_lines.append(line)
                if line_callback is not None:
                    line_callback(line)
        if not got:
            time.sleep(0.2)

    rc = proc.returncode or 0
    if rc != 0:
        # When stderr is merged into stdout (STDOUT), the error is in stdout_lines;
        # when stderr is a separate pipe, read from it.
        if stderr == subprocess.PIPE and proc.stderr:
            err_tail = proc.stderr.read()[-500:]
        else:
            err_tail = "".join(stdout_lines).strip()[-800:]
        raise LlmTransportError(f"{name} 失败(code={rc}): {err_tail}")

    return stdout_lines
