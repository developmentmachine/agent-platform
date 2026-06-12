"""LLM 客户端 — 支持 client 缓存和网络重试。"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

from agent_platform.config.settings import Settings

logger = logging.getLogger("agent_platform.agents.hsk30_tutor.llm_client")

# ── Client 缓存 ──────────────────────────────────────────────
_cached_client: Any = None
_cached_key: Tuple[Optional[str], Optional[str]] = (None, None)


def _get_client(settings: Settings) -> Any:
    """获取或创建 OpenAI client（按 api_key + base_url 缓存）。"""
    global _cached_client, _cached_key
    key = (settings.openai_api_key, settings.openai_base_url)
    if _cached_client is not None and _cached_key == key:
        return _cached_client

    try:
        from openai import OpenAI
    except ImportError as e:
        raise ImportError(f"openai package unavailable: {e}") from e

    _cached_client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.timeout_s,
    )
    _cached_key = key
    return _cached_client


# ── 重试逻辑 ─────────────────────────────────────────────────
_MAX_RETRIES = 2
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _retry_delay(attempt: int, base: float = 1.0) -> float:
    """指数退避：1s, 2s。"""
    return base * (2 ** attempt)


def chat_completion(
    settings: Settings,
    messages: List[Dict[str, str]],
) -> Tuple[str, str]:
    """返回 ``(reply_text, backend_tag)``。无 API Key 时走 stub。"""
    if not (settings.openai_api_key or "").strip():
        return _stub_from_messages(messages), "stub"

    try:
        client = _get_client(settings)
    except ImportError as e:
        logger.warning("%s", e)
        return _stub_from_messages(messages), "stub"

    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=settings.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=settings.temperature,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                return _stub_from_messages(messages), "stub"
            return text, "llm"
        except Exception as exc:
            # 检查是否可重试
            status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            if isinstance(status, int) and status in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                delay = _retry_delay(attempt)
                logger.warning("LLM request failed (status=%s), retry %d/%d in %.1fs",
                               status, attempt + 1, _MAX_RETRIES, delay)
                time.sleep(delay)
                continue
            # 不可重试的错误
            logger.error("LLM request failed: %s", exc)
            break

    return _stub_from_messages(messages), "stub"


def chat_completion_stream(
    settings: Settings,
    messages: List[Dict[str, str]],
) -> Iterator[Tuple[str, str]]:
    """流式返回 ``(chunk_text, backend_tag)``。"""
    if not (settings.openai_api_key or "").strip():
        yield _stub_from_messages(messages), "stub"
        return

    try:
        client = _get_client(settings)
    except ImportError as e:
        logger.warning("%s", e)
        yield _stub_from_messages(messages), "stub"
        return

    for attempt in range(_MAX_RETRIES + 1):
        try:
            stream = client.chat.completions.create(
                model=settings.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=settings.temperature,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content, "llm"
            return  # 成功完成
        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            if isinstance(status, int) and status in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                delay = _retry_delay(attempt)
                logger.warning("LLM stream failed (status=%s), retry %d/%d in %.1fs",
                               status, attempt + 1, _MAX_RETRIES, delay)
                time.sleep(delay)
                continue
            logger.error("LLM stream failed: %s", exc)
            break

    yield _stub_from_messages(messages), "stub"


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
