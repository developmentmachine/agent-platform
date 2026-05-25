"""QQ Bot connector — botpy 长连接 + AgentRuntime 路由。"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agent_platform.adapters.qq.dedup import MsgIdDedup
from agent_platform.adapters.reply_chunks import split_reply_chunks
from agent_platform.adapters.qq.frame_mapper import (
    map_qq_c2c_message,
    map_qq_group_message,
)
from agent_platform.adapters.qq.message_normalizer import normalize_qq_text
from agent_platform.adapters.qq.ws_auth import QqWsAuthMode, parse_qq_ws_auth_mode
from agent_platform.runtime import AgentRuntime

logger = logging.getLogger("agent_platform.adapters.qq.connector")

QQ_BOT_DEFAULT_INTENTS = 0
# 单条文本建议长度（官方未公布硬上限）；长文通过分片发送，不在 adapter 截断。
QQ_MESSAGE_MAX_CHARS = 1800
# 被动回复同一 msg_id 最多 5 次（QQ 开放平台）；超出部分走主动消息。
QQ_PASSIVE_REPLY_LIMIT = 5


def _resolve_app_secret(env: Dict[str, str]) -> Optional[str]:
    for key in ("QQ_BOT_CLIENT_SECRET", "QQ_BOT_APP_SECRET"):
        raw = (env.get(key) or "").strip()
        if raw:
            return raw
    return None


@dataclass
class QqBotConnectorOptions:
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    bot_user_id: Optional[str] = None
    intents: int = QQ_BOT_DEFAULT_INTENTS
    ws_auth_mode: QqWsAuthMode = "app_token"
    enabled: bool = True
    default_agent_id: str = "stock-recap"
    tenant_id: Optional[str] = None
    recap_provider: str = "live"
    recap_force_llm: bool = True
    recap_model: Optional[str] = None
    recap_skip_trading_check: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


def load_qq_options_from_env(env: Optional[Dict[str, str]] = None) -> QqBotConnectorOptions:
    """从环境变量或 ``Settings``（含 ``.env``）加载 QQ Bot 配置。"""
    if env is not None:
        return _qq_options_from_mapping(env)
    from agent_platform.config.settings import get_settings

    return load_qq_options_from_settings(get_settings())


def load_qq_options_from_settings(settings: Any) -> QqBotConnectorOptions:
    """从 ``Settings`` 实例构建（``__main__`` / 生产推荐路径）。"""
    recap_model = settings.qq_bot_recap_model or settings.model
    return QqBotConnectorOptions(
        app_id=(settings.qq_bot_app_id or "").strip() or None,
        app_secret=(settings.qq_bot_client_secret or "").strip() or None,
        bot_user_id=(settings.qq_bot_user_id or "").strip() or None,
        intents=QQ_BOT_DEFAULT_INTENTS,
        enabled=bool(settings.qq_bot_enabled),
        default_agent_id=(settings.qq_default_agent_id or "stock-recap").strip(),
        recap_provider=(settings.qq_bot_recap_provider or "live").strip(),
        recap_force_llm=bool(settings.qq_bot_recap_force_llm),
        recap_model=(recap_model or "").strip() or None,
        recap_skip_trading_check=bool(settings.qq_bot_recap_skip_trading_check),
    )


def _qq_options_from_mapping(env: Dict[str, str]) -> QqBotConnectorOptions:
    enabled_raw = (env.get("QQ_BOT_ENABLED") or "true").strip().lower()
    force_llm_raw = (env.get("QQ_BOT_RECAP_FORCE_LLM") or "true").strip().lower()
    skip_trading_raw = (env.get("QQ_BOT_RECAP_SKIP_TRADING_CHECK") or "false").strip().lower()
    return QqBotConnectorOptions(
        app_id=(env.get("QQ_BOT_APP_ID") or "").strip() or None,
        app_secret=_resolve_app_secret(env),
        bot_user_id=(env.get("QQ_BOT_USER_ID") or "").strip() or None,
        intents=int(env.get("QQ_BOT_INTENTS") or QQ_BOT_DEFAULT_INTENTS),
        ws_auth_mode=parse_qq_ws_auth_mode(env.get("QQ_BOT_WS_AUTH_MODE")),
        enabled=enabled_raw not in ("0", "false", "no"),
        default_agent_id=(env.get("QQ_DEFAULT_AGENT_ID") or "stock-recap").strip(),
        tenant_id=(env.get("QQ_TENANT_ID") or "").strip() or None,
        recap_provider=(env.get("QQ_BOT_RECAP_PROVIDER") or "live").strip(),
        recap_force_llm=force_llm_raw not in ("0", "false", "no"),
        recap_model=(env.get("QQ_BOT_RECAP_MODEL") or env.get("RECAP_MODEL") or "").strip()
        or None,
        recap_skip_trading_check=skip_trading_raw in ("1", "true", "yes"),
    )


class QqBotConnector:
    """QQ Bot 连接器：group @ / c2c / 频道 @ → ``AgentRuntime.run``。"""

    def __init__(
        self,
        *,
        options: QqBotConnectorOptions,
        runtime: AgentRuntime,
        reply_sender: Optional[Callable[[List[str], Dict[str, Any]], None]] = None,
    ) -> None:
        self._opts = options
        self._runtime = runtime
        self._dedup = MsgIdDedup()
        self._reply_sender = reply_sender or self._default_reply_sender

    def start(self) -> None:
        """阻塞运行 botpy WebSocket 长连接。"""
        if not self._opts.enabled:
            logger.info("qq bot connector disabled")
            return
        if not (self._opts.app_id and self._opts.app_secret):
            logger.warning("qq bot connector missing app_id/app_secret; not starting")
            return
        import asyncio

        from agent_platform.adapters.qq.botpy_client import build_botpy_client

        # Python 3.10+ 主线程默认无 event loop；botpy.Client.__init__ 会 get_event_loop()
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        client = build_botpy_client(self)
        logger.info(
            "qq bot starting: app_id=%s agent=%s provider=%s",
            self._opts.app_id,
            self._opts.default_agent_id,
            self._opts.recap_provider,
        )
        client.run(appid=self._opts.app_id, secret=self._opts.app_secret)

    def handle_group_message(self, frame: Dict[str, Any]) -> Optional[list[str]]:
        return self._dispatch(frame, kind="group")

    def handle_c2c_message(self, frame: Dict[str, Any]) -> Optional[list[str]]:
        return self._dispatch(frame, kind="c2c")

    def _dispatch(self, frame: Dict[str, Any], *, kind: str) -> Optional[list[str]]:
        msg_id = str(frame.get("id") or frame.get("msg_id") or "")
        if msg_id and self._dedup.seen(msg_id):
            return None

        if kind == "group":
            principal, conv_key = map_qq_group_message(frame, tenant_id=self._opts.tenant_id)
        else:
            principal, conv_key = map_qq_c2c_message(frame, tenant_id=self._opts.tenant_id)
        normalized = normalize_qq_text(frame, bot_user_id=self._opts.bot_user_id)
        if not normalized.text:
            return None

        # 群 @ 事件（group_at）在 frame 上标记；普通群消息仍需 @bot
        if kind == "group" and not normalized.is_at_bot and not frame.get("_group_at"):
            return None

        try:
            resp = self._runtime.run(
                agent_id=self._opts.default_agent_id,
                payload=self._payload_for_agent(normalized.text),
                principal=principal,
                conversation_key=conv_key,
            )
        except Exception as e:
            logger.exception("qq runtime.run failed")
            return [f"⚠ 处理失败：{e}"]

        if resp.errors:
            return [f"⚠ {resp.errors[0]}"]

        rendered = (
            resp.rendered.get("wechat_text")
            or resp.rendered.get("markdown")
            or ""
        )
        if not rendered and isinstance(resp.payload, dict):
            err = resp.payload.get("error")
            if err:
                rendered = f"⚠ {err}"
        if not rendered:
            rendered = "（未生成正文，请稍后重试）"

        chunks = split_reply_chunks(rendered, max_chars=QQ_MESSAGE_MAX_CHARS)
        self._reply_sender(
            chunks,
            {
                "msg_id": msg_id,
                "principal": principal.subject,
                "kind": kind,
                "frame": frame,
            },
        )
        return chunks

    def _payload_for_agent(self, text: str) -> Dict[str, Any]:
        mode = "strategy" if ("策略" in text or "明天" in text or "次日" in text) else "daily"
        payload: Dict[str, Any] = {
            "mode": mode,
            "provider": self._opts.recap_provider,
            "force_llm": self._opts.recap_force_llm,
            "skip_trading_check": self._opts.recap_skip_trading_check,
        }
        if self._opts.recap_model:
            payload["model"] = self._opts.recap_model
        return payload

    def _default_reply_sender(self, chunks: list[str], meta: Dict[str, Any]) -> None:
        total_len = sum(len(c) for c in chunks)
        logger.info(
            "qq reply (sdk handles send): kind=%s msg_id=%s parts=%s len=%s",
            meta.get("kind"),
            meta.get("msg_id"),
            len(chunks),
            total_len,
        )


__all__ = [
    "QqBotConnector",
    "QqBotConnectorOptions",
    "load_qq_options_from_env",
    "load_qq_options_from_settings",
    "QQ_BOT_DEFAULT_INTENTS",
    "QQ_MESSAGE_MAX_CHARS",
    "QQ_PASSIVE_REPLY_LIMIT",
]
