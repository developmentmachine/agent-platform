"""企业微信 AiBot connector — WebSocket 长连接 + HTTP 回调（webhook）双模式。

- **长连接**：``start()`` → ``ws_client.run_wecom_ws_loop``（``wss://openws.work.weixin.qq.com``）
- **短连接**：``adapters/wecom/webhook`` AES 回调（无需公网入站时长连接）
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from agent_platform.adapters.wecom.dedup import MsgIdDedup
from agent_platform.adapters.wecom.frame_mapper import map_wecom_frame
from agent_platform.adapters.wecom.message_normalizer import normalize_wecom_text
from agent_platform.adapters.wecom.stream_reply import StreamReplyBuffer
from agent_platform.runtime import AgentRuntime

logger = logging.getLogger("agent_platform.adapters.wecom.connector")


@dataclass
class WecomAiBotConnectorOptions:
    """从环境变量或显式构造。"""

    corp_id: Optional[str] = None
    secret: Optional[str] = None
    bot_id: Optional[str] = None
    encoding_aes_key: Optional[str] = None
    enabled: bool = True
    welcome_message: str = "你好，我是 Agent Platform Bot，直接发送消息即可对话。"
    default_agent_id: str = "stock-recap"
    tenant_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


def load_wecom_options_from_env(env: Optional[Dict[str, str]] = None) -> WecomAiBotConnectorOptions:
    env = env or os.environ  # type: ignore[assignment]
    enabled_raw = (env.get("WECOM_AIBOT_ENABLED") or "true").strip().lower()
    enabled = enabled_raw not in ("0", "false", "no")
    return WecomAiBotConnectorOptions(
        corp_id=(env.get("WECOM_CORP_ID") or "").strip() or None,
        secret=(env.get("WECOM_SECRET") or "").strip() or None,
        bot_id=(env.get("WECOM_AIBOT_BOT_ID") or "").strip() or None,
        encoding_aes_key=(env.get("WECOM_ENCODING_AES_KEY") or "").strip() or None,
        enabled=enabled,
        welcome_message=(env.get("WECOM_AIBOT_WELCOME") or "").strip()
        or "你好，我是 Agent Platform Bot，直接发送消息即可对话。",
        default_agent_id=(env.get("WECOM_DEFAULT_AGENT_ID") or "stock-recap").strip(),
        tenant_id=(env.get("WECOM_TENANT_ID") or "").strip() or None,
    )


class WecomAiBotConnector:
    """企业微信 AiBot 连接器。

    生命周期：``start()`` → 阻塞接收消息 → 收到 frame 后调用 ``handle_frame``。

    ``handle_frame`` 已与 SDK 解耦：测试 / dev 模式可手工灌入 frame 即可走完
    完整链路（normalize → dedup → runtime.run → reply）。
    """

    def __init__(
        self,
        *,
        options: WecomAiBotConnectorOptions,
        runtime: AgentRuntime,
        reply_sender: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        self._opts = options
        self._runtime = runtime
        self._dedup = MsgIdDedup()
        # 注入式的回复发送器：测试时传 lambda 收集；生产环境注入 SDK 调用。
        self._reply_sender = reply_sender or self._default_reply_sender

    def start(self) -> None:
        if not self._opts.enabled:
            logger.info("wecom aibot connector disabled")
            return
        if not (self._opts.bot_id and self._opts.secret):
            logger.warning("wecom aibot connector missing bot_id/secret; not starting")
            return
        mode = (os.environ.get("WECOM_AIBOT_MODE") or "websocket").strip().lower()
        if mode in ("webhook", "callback", "http"):
            logger.info(
                "wecom mode=%s: 请用 HTTP 服务暴露 /v1/adapters/wecom/callback（见 adapters/wecom/webhook）",
                mode,
            )
            return
        from agent_platform.adapters.wecom.ws_client import run_wecom_ws_loop

        ws_url = (os.environ.get("WECOM_AIBOT_WS_URL") or "").strip() or None
        logger.info("wecom aibot websocket connecting (bot_id=%s)", self._opts.bot_id)
        run_wecom_ws_loop(self, ws_url=ws_url or "wss://openws.work.weixin.qq.com")

    def handle_frame(self, frame: Dict[str, Any], *, send_reply: bool = True) -> Optional[str]:
        """处理单条入站消息；返回回复文本（或 None）。

        生产环境由 SDK 回调驱动；测试 / dev 直接调用本方法即可。
        """
        msg_id = str(frame.get("msg_id") or frame.get("message_id") or "")
        if self._dedup.seen(msg_id):
            logger.debug("wecom duplicate msg dropped: %s", msg_id)
            return None

        principal, conv_key = map_wecom_frame(frame, tenant_id=self._opts.tenant_id)
        normalized = normalize_wecom_text(frame, bot_name=self._opts.bot_id)

        if not normalized.text:
            return None

        envelope_payload: Dict[str, Any] = {"message": normalized.text}
        if self._opts.default_agent_id == "stock-recap":
            # stock-recap 对话型触发：把消息当成 mode 切换的简单 keyword
            envelope_payload = self._payload_for_stock_recap(normalized.text)

        try:
            resp = self._runtime.run(
                agent_id=self._opts.default_agent_id,
                payload=envelope_payload,
                principal=principal,
                conversation_key=conv_key,
            )
        except Exception as e:
            logger.exception("wecom runtime.run failed")
            return f"⚠ 抱歉，处理失败：{e}"

        rendered = resp.rendered.get("wechat_text") or resp.rendered.get("markdown") or str(resp.payload)
        if send_reply:
            self._reply_sender(rendered, {"msg_id": msg_id, "principal": principal.subject})
        return rendered

    # ─── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _payload_for_stock_recap(text: str) -> Dict[str, Any]:
        """超薄触发逻辑：消息含 ``策略`` → strategy；否则默认 daily。

        真正的对话路由（"今天市场怎么样" → daily）放到后续 commit 中独立的
        ``IntentRouter`` 实现。
        """
        mode = "strategy" if ("策略" in text or "明天" in text) else "daily"
        return {"mode": mode, "provider": "live"}

    def _default_reply_sender(self, text: str, meta: Dict[str, Any]) -> None:
        """SDK 未接入时的占位 sender — 仅记录日志。"""
        logger.info("wecom reply (no sdk): msg_id=%s text=%s", meta.get("msg_id"), text[:200])


__all__ = [
    "WecomAiBotConnector",
    "WecomAiBotConnectorOptions",
    "load_wecom_options_from_env",
]
