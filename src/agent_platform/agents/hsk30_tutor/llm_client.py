"""LLM 客户端 — 支持 client 缓存和网络重试。

重构要点：
- _ensure_client 统一"无 key → stub / 有 key → client"逻辑
- _retry_loop 提取重试循环
- chat_completion 和 chat_completion_stream 共享基础设施但各自处理返回语义
"""
from __future__ import annotations

import functools
import logging
import threading
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from agent_platform.config.settings import Settings

logger = logging.getLogger("agent_platform.agents.hsk30_tutor.llm_client")

# ── 常量 ────────────────────────────────────────────────────
_MAX_RETRIES = 2
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# ── Client 缓存（线程安全）──────────────────────────────────
_client_lock = threading.Lock()
_cached_client: Any = None
_cached_key: Tuple[Optional[str], Optional[str]] = (None, None)


def _get_client(settings: Settings) -> Any:
    """获取或创建 OpenAI client（按 api_key + base_url 缓存，线程安全）。"""
    global _cached_client, _cached_key
    key = (settings.openai_api_key, settings.openai_base_url)
    # Fast path: 无锁读（已缓存且 key 匹配）
    if _cached_client is not None and _cached_key == key:
        return _cached_client

    with _client_lock:
        # Double-check: 拿到锁后再检查一次
        if _cached_client is not None and _cached_key == key:
            return _cached_client

        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(f"openai package unavailable: {e}") from e

        _cached_client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url,
                                timeout=settings.timeout_s)
        _cached_key = key
        return _cached_client


def _stub_from_messages(messages: List[Dict[str, str]]) -> str:
    """从消息列表中提取最后一条用户消息，生成 stub 回复。"""
    user = next((m.get("content", "").strip() for m in reversed(messages) if m.get("role") == "user"), "")
    return (
        "【陪练模式 · 未配置 OPENAI_API_KEY，使用本地占位回复】\n\n"
        f"收到：{user or '（空）'}\n\n"
        "建议自查：\n"
        "1. 句子是否为主谓宾完整？\n"
        "2. 量词、了/过/着 是否用对？\n"
        "3. 请用更短的句子再试一次。\n\n"
        "配置 OPENAI_API_KEY 后可获得完整 AI 纠错与讲解。"
    )


# ── 基础设施 ────────────────────────────────────────────────

def _is_retryable(exc: BaseException) -> bool:
    """判断异常是否可重试（HTTP 429/5xx、连接/超时/限流）。"""
    # HTTP status code (openai.APIStatusError)
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(status, int) and status in _RETRYABLE_STATUS:
        return True
    # openai.APIConnectionError, APITimeoutError, RateLimitError
    exc_name = type(exc).__name__
    if exc_name in ("APIConnectionError", "APITimeoutError", "RateLimitError"):
        return True
    return False


def _retry_loop(fn: Callable[[], Any], max_retries: int = _MAX_RETRIES) -> Any:
    """通用重试循环：执行 fn()，可重试异常自动退避重试（基于 tenacity）。"""
    for attempt in Retrying(
        stop=stop_after_attempt(max_retries + 1),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    ):
        with attempt:
            return fn()


def _ensure_client(settings: Settings, messages: List[Dict[str, str]]) -> Tuple[Any, str]:
    """检查 API Key 并返回 client；无 key 或 import 失败时返回 (None, stub_reply)。

    Returns:
        (client, "") if client is ready, or (None, stub_text) if fallback.
    """
    if not (settings.openai_api_key or "").strip():
        return None, _stub_from_messages(messages)
    try:
        return _get_client(settings), ""
    except ImportError as e:
        logger.warning("%s", e)
        return None, _stub_from_messages(messages)


# ── 对外接口 ─────────────────────────────────────────────────

def chat_completion(
    settings: Settings,
    messages: List[Dict[str, str]],
) -> Tuple[str, str]:
    """返回 ``(reply_text, backend_tag)``。无 API Key 时走 stub。"""
    client, stub = _ensure_client(settings, messages)
    if client is None:
        return stub, "stub"

    try:
        resp = _retry_loop(lambda: client.chat.completions.create(
            model=settings.model, messages=messages, temperature=settings.temperature))
        text = (resp.choices[0].message.content or "").strip()
        return (text, "llm") if text else (_stub_from_messages(messages), "stub")
    except Exception as exc:
        logger.error("LLM request failed: %s", exc)
        return _stub_from_messages(messages), "stub"


def chat_completion_stream(
    settings: Settings,
    messages: List[Dict[str, str]],
) -> Iterator[Tuple[str, str]]:
    """流式返回 ``(chunk_text, backend_tag)``。"""
    client, stub = _ensure_client(settings, messages)
    if client is None:
        yield stub, "stub"
        return

    try:
        stream = _retry_loop(lambda: client.chat.completions.create(
            model=settings.model, messages=messages, temperature=settings.temperature, stream=True))
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content, "llm"
    except Exception as exc:
        logger.error("LLM stream failed: %s", exc)
        yield _stub_from_messages(messages), "stub"
