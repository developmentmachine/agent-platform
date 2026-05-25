"""轻量文本对话 LLM 客户端（与 recap 结构化 ``call_llm`` 解耦）。"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from agent_platform.config.settings import Settings

logger = logging.getLogger("agent_platform.agents.hsk30_tutor.llm_client")


def chat_completion(
    settings: Settings,
    messages: List[Dict[str, str]],
) -> Tuple[str, str]:
    """返回 ``(reply_text, backend_tag)``。无 API Key 时走 stub。"""
    if not (settings.openai_api_key or "").strip():
        return _stub_from_messages(messages), "stub"

    try:
        from openai import OpenAI
    except ImportError as e:
        logger.warning("openai package unavailable: %s", e)
        return _stub_from_messages(messages), "stub"

    client = OpenAI(api_key=settings.openai_api_key, timeout=settings.timeout_s)
    resp = client.chat.completions.create(
        model=settings.model,
        messages=messages,  # type: ignore[arg-type]
        temperature=settings.temperature,
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        return _stub_from_messages(messages), "stub"
    return text, "llm"


def _stub_from_messages(messages: List[Dict[str, str]]) -> str:
    user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user = (m.get("content") or "").strip()
            break
    if not user:
        user = "（空）"
    return (
        "【陪练模式 · 未配置 OPENAI_API_KEY，使用本地占位回复】\n\n"
        f"收到：{user}\n\n"
        "建议自查：\n"
        "1. 句子是否为主谓宾完整？\n"
        "2. 量词、了/过/着 是否用对？\n"
        "3. 请用更短的句子再试一次。\n\n"
        "配置 OPENAI_API_KEY 后可获得完整 AI 纠错与讲解。"
    )
