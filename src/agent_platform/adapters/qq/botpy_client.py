"""botpy.Client 适配 — 把官方 SDK 的事件桥接到 ``QqBotConnector`` (W5)。

事件覆盖（与 ares-agent-pkx 一致的 surface）：
- ``on_at_message_create``        频道 @机器人（公域消息）
- ``on_group_at_message_create``  QQ 群 @机器人
- ``on_c2c_message_create``       QQ 私聊
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from agent_platform.adapters.qq.connector import QQ_PASSIVE_REPLY_LIMIT

logger = logging.getLogger("agent_platform.adapters.qq.botpy_client")


def _frame_from_group_message(message: Any, *, group_at: bool = False) -> Dict[str, Any]:
    """把 botpy.message.GroupMessage 序列化为 ``handle_group_message`` 期望的 dict。"""
    frame: Dict[str, Any] = {
        "id": getattr(message, "id", None),
        "msg_id": getattr(message, "id", None),
        "content": getattr(message, "content", "") or "",
        "group_openid": getattr(message, "group_openid", None),
        "author": {"id": getattr(getattr(message, "author", None), "id", None)},
        "_sdk_message": message,
    }
    if group_at:
        frame["_group_at"] = True
    return frame


def _frame_from_c2c_message(message: Any) -> Dict[str, Any]:
    return {
        "id": getattr(message, "id", None),
        "msg_id": getattr(message, "id", None),
        "content": getattr(message, "content", "") or "",
        "author": {
            "id": getattr(getattr(message, "author", None), "user_openid", None)
            or getattr(getattr(message, "author", None), "id", None)
        },
        "_sdk_message": message,
    }


def _frame_from_at_message(message: Any) -> Dict[str, Any]:
    frame = {
        "id": getattr(message, "id", None),
        "msg_id": getattr(message, "id", None),
        "content": getattr(message, "content", "") or "",
        "channel_id": getattr(message, "channel_id", None),
        "guild_id": getattr(message, "guild_id", None),
        "author": {"id": getattr(getattr(message, "author", None), "id", None)},
        "_sdk_message": message,
        "_group_at": True,
    }
    return frame


async def _send_chunked_reply(message: Any, chunks: List[str]) -> None:
    """分片发送：前 ``QQ_PASSIVE_REPLY_LIMIT`` 条为被动回复（msg_seq），其余为主动消息。"""
    if not chunks:
        return
    api = message._api
    msg_id = getattr(message, "id", None)

    for idx, content in enumerate(chunks):
        msg_seq = idx + 1
        try:
            if msg_seq <= QQ_PASSIVE_REPLY_LIMIT and msg_id:
                await message.reply(content=content, msg_seq=msg_seq)
                continue

            group_openid = getattr(message, "group_openid", None)
            if group_openid:
                await api.post_group_message(
                    group_openid=group_openid,
                    content=content,
                    msg_type=0,
                )
                continue

            user_openid = getattr(getattr(message, "author", None), "user_openid", None)
            if user_openid:
                await api.post_c2c_message(
                    openid=user_openid,
                    content=content,
                    msg_type=0,
                )
                continue

            await message.reply(content=content, msg_seq=min(msg_seq, QQ_PASSIVE_REPLY_LIMIT))
        except Exception:
            logger.exception(
                "qq send chunk failed: part=%s/%s passive=%s",
                msg_seq,
                len(chunks),
                msg_seq <= QQ_PASSIVE_REPLY_LIMIT,
            )
            raise


def build_botpy_client(connector: Any):
    """构造 botpy.Client 子类，事件转发至 connector。

    复盘在 ``run_in_executor`` 中执行，避免阻塞 asyncio 事件循环。
    """
    import botpy

    intents = botpy.Intents(
        public_messages=True,
        public_guild_messages=True,
        direct_message=True,
    )

    class _PlatformBotpyClient(botpy.Client):  # type: ignore[misc]
        async def on_ready(self):
            robot = getattr(self, "robot", None)
            name = getattr(robot, "name", None) if robot else None
            logger.info("qq botpy ready: bot=%s", name or "?")

        async def _run_handler(self, handler_name: str, frame: Dict[str, Any]) -> Optional[List[str]]:
            loop = asyncio.get_running_loop()
            handler = getattr(connector, handler_name)
            return await loop.run_in_executor(None, lambda: handler(frame))

        async def _reply_chunks(self, message: Any, chunks: Optional[List[str]]) -> None:
            if chunks:
                await _send_chunked_reply(message, chunks)

        async def on_group_at_message_create(self, message):
            frame = _frame_from_group_message(message, group_at=True)
            chunks = await self._run_handler("handle_group_message", frame)
            await self._reply_chunks(message, chunks)

        async def on_c2c_message_create(self, message):
            frame = _frame_from_c2c_message(message)
            chunks = await self._run_handler("handle_c2c_message", frame)
            await self._reply_chunks(message, chunks)

        async def on_at_message_create(self, message):
            frame = _frame_from_at_message(message)
            chunks = await self._run_handler("handle_group_message", frame)
            await self._reply_chunks(message, chunks)

    return _PlatformBotpyClient(intents=intents)


__all__ = [
    "build_botpy_client",
    "_frame_from_group_message",
    "_frame_from_c2c_message",
    "_frame_from_at_message",
    "_send_chunked_reply",
]
