"""QQ Bot connector 骨架（W1：仅类型与协议）。"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from agent_platform.adapters.qq.dedup import MsgIdDedup
from agent_platform.adapters.qq.frame_mapper import (
    map_qq_c2c_message,
    map_qq_group_message,
)
from agent_platform.adapters.qq.message_normalizer import normalize_qq_text
from agent_platform.adapters.qq.ws_auth import QqWsAuthMode, parse_qq_ws_auth_mode
from agent_platform.runtime import AgentRuntime

logger = logging.getLogger("agent_platform.adapters.qq.connector")

QQ_BOT_DEFAULT_INTENTS = 0  # 占位；接入时按 botpy 文档填充实际位


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
    extra: Dict[str, Any] = field(default_factory=dict)


def load_qq_options_from_env(env: Optional[Dict[str, str]] = None) -> QqBotConnectorOptions:
    env = env or os.environ  # type: ignore[assignment]
    enabled_raw = (env.get("QQ_BOT_ENABLED") or "true").strip().lower()
    enabled = enabled_raw not in ("0", "false", "no")
    return QqBotConnectorOptions(
        app_id=(env.get("QQ_BOT_APP_ID") or "").strip() or None,
        app_secret=(env.get("QQ_BOT_APP_SECRET") or "").strip() or None,
        bot_user_id=(env.get("QQ_BOT_USER_ID") or "").strip() or None,
        intents=int(env.get("QQ_BOT_INTENTS") or QQ_BOT_DEFAULT_INTENTS),
        ws_auth_mode=parse_qq_ws_auth_mode(env.get("QQ_BOT_WS_AUTH_MODE")),
        enabled=enabled,
        default_agent_id=(env.get("QQ_DEFAULT_AGENT_ID") or "stock-recap").strip(),
        tenant_id=(env.get("QQ_TENANT_ID") or "").strip() or None,
    )


class QqBotConnector:
    """QQ Bot 连接器骨架，支持 group / c2c 两种入站消息。"""

    def __init__(
        self,
        *,
        options: QqBotConnectorOptions,
        runtime: AgentRuntime,
        reply_sender: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        self._opts = options
        self._runtime = runtime
        self._dedup = MsgIdDedup()
        self._reply_sender = reply_sender or self._default_reply_sender

    def start(self) -> None:
        if not self._opts.enabled:
            logger.info("qq bot connector disabled")
            return
        if not (self._opts.app_id and self._opts.app_secret):
            logger.warning("qq bot connector missing app_id/app_secret; not starting")
            return
        # TODO(next-commit): 接入 botpy / 自实现 WebSocket
        logger.info("qq bot connector scaffolded (SDK integration pending)")

    def handle_group_message(self, frame: Dict[str, Any]) -> Optional[str]:
        return self._dispatch(frame, kind="group")

    def handle_c2c_message(self, frame: Dict[str, Any]) -> Optional[str]:
        return self._dispatch(frame, kind="c2c")

    # ─── helpers ──────────────────────────────────────────────────────────

    def _dispatch(self, frame: Dict[str, Any], *, kind: str) -> Optional[str]:
        msg_id = str(frame.get("id") or frame.get("msg_id") or "")
        if self._dedup.seen(msg_id):
            return None

        if kind == "group":
            principal, conv_key = map_qq_group_message(frame, tenant_id=self._opts.tenant_id)
        else:
            principal, conv_key = map_qq_c2c_message(frame, tenant_id=self._opts.tenant_id)
        normalized = normalize_qq_text(frame, bot_user_id=self._opts.bot_user_id)
        if not normalized.text:
            return None

        # 群消息默认要求 @bot；C2C 直接处理
        if kind == "group" and not normalized.is_at_bot:
            return None

        try:
            resp = self._runtime.run(
                agent_id=self._opts.default_agent_id,
                payload=self._payload_for_default_agent(normalized.text),
                principal=principal,
                conversation_key=conv_key,
            )
        except Exception as e:
            logger.exception("qq runtime.run failed")
            return f"⚠ 抱歉，处理失败：{e}"

        rendered = resp.rendered.get("markdown") or resp.rendered.get("wechat_text") or str(resp.payload)
        self._reply_sender(rendered, {"msg_id": msg_id, "principal": principal.subject, "kind": kind})
        return rendered

    @staticmethod
    def _payload_for_default_agent(text: str) -> Dict[str, Any]:
        mode = "strategy" if ("策略" in text or "明天" in text) else "daily"
        return {"mode": mode, "provider": "live"}

    def _default_reply_sender(self, text: str, meta: Dict[str, Any]) -> None:
        logger.info("qq reply (no sdk): kind=%s msg_id=%s text=%s", meta.get("kind"), meta.get("msg_id"), text[:200])


__all__ = ["QqBotConnector", "QqBotConnectorOptions", "load_qq_options_from_env", "QQ_BOT_DEFAULT_INTENTS"]
