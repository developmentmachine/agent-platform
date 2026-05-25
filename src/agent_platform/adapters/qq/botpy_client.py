"""botpy.Client 适配 — 把官方 SDK 的事件桥接到 ``QqBotConnector`` (W5)。

事件覆盖（与 ares-pkx 一致的 surface）：
- ``on_at_message_create``        频道 @机器人（公域消息）
- ``on_group_at_message_create``  QQ 群 @机器人
- ``on_c2c_message_create``       QQ 私聊
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("agent_platform.adapters.qq.botpy_client")


def _frame_from_group_message(message: Any) -> Dict[str, Any]:
    """把 botpy.message.GroupMessage 序列化为 ``handle_group_message`` 期望的 dict。"""
    return {
        "id": getattr(message, "id", None),
        "msg_id": getattr(message, "id", None),
        "content": getattr(message, "content", "") or "",
        "group_openid": getattr(message, "group_openid", None),
        "author": {"id": getattr(getattr(message, "author", None), "id", None)},
        "_sdk_message": message,
    }


def _frame_from_c2c_message(message: Any) -> Dict[str, Any]:
    return {
        "id": getattr(message, "id", None),
        "msg_id": getattr(message, "id", None),
        "content": getattr(message, "content", "") or "",
        "author": {"id": getattr(getattr(message, "author", None), "user_openid", None)
                          or getattr(getattr(message, "author", None), "id", None)},
        "_sdk_message": message,
    }


def _frame_from_at_message(message: Any) -> Dict[str, Any]:
    return {
        "id": getattr(message, "id", None),
        "msg_id": getattr(message, "id", None),
        "content": getattr(message, "content", "") or "",
        "channel_id": getattr(message, "channel_id", None),
        "guild_id": getattr(message, "guild_id", None),
        "author": {"id": getattr(getattr(message, "author", None), "id", None)},
        "_sdk_message": message,
    }


def build_botpy_client(connector: Any):
    """构造 botpy.Client 子类，事件转发至 connector。

    必须 lazy 导入 botpy（重 SDK；测试常需 monkeypatch）。
    """
    import botpy

    intents = botpy.Intents(
        public_messages=True,        # group + c2c
        public_guild_messages=True,  # @bot in channels
    )

    class _PlatformBotpyClient(botpy.Client):  # type: ignore[misc]
        async def on_ready(self):
            logger.info("qq botpy ready: bot=%s", getattr(self.robot, "name", "?"))

        async def on_group_at_message_create(self, message):
            frame = _frame_from_group_message(message)
            reply = connector.handle_group_message(frame)
            if reply:
                try:
                    await message.reply(content=reply)
                except Exception:
                    logger.exception("qq group reply failed")

        async def on_c2c_message_create(self, message):
            frame = _frame_from_c2c_message(message)
            reply = connector.handle_c2c_message(frame)
            if reply:
                try:
                    await message.reply(content=reply)
                except Exception:
                    logger.exception("qq c2c reply failed")

        async def on_at_message_create(self, message):
            frame = _frame_from_at_message(message)
            # 频道 @bot 走 group handler（语义最接近 — 都是公开多人场景）
            reply = connector.handle_group_message(frame)
            if reply:
                try:
                    await message.reply(content=reply)
                except Exception:
                    logger.exception("qq at_message reply failed")

    return _PlatformBotpyClient(intents=intents)


__all__ = [
    "build_botpy_client",
    "_frame_from_group_message",
    "_frame_from_c2c_message",
    "_frame_from_at_message",
]
