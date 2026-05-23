"""企业微信智能机器人 WebSocket 长连接客户端。"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional

from agent_platform.adapters.wecom.ws_protocol import (
    WECOM_WS_URL,
    build_ping,
    build_respond_stream,
    build_subscribe,
    is_subscribe_ok,
    map_aibot_callback_to_frame,
    new_req_id,
)

logger = logging.getLogger("agent_platform.adapters.wecom.ws_client")

_HEARTBEAT_INTERVAL_S = 30.0
_RECV_TIMEOUT_S = 90.0


async def _heartbeat(ws: Any, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=_HEARTBEAT_INTERVAL_S)
            break
        except asyncio.TimeoutError:
            pass
        try:
            await ws.send(json.dumps(build_ping(), ensure_ascii=False))
        except Exception as e:
            logger.warning("wecom ws ping failed: %s", e)
            break


async def _run_wecom_ws_async(connector: Any, *, ws_url: str = WECOM_WS_URL) -> None:
    import websockets

    opts = connector._opts
    bot_id = opts.bot_id
    secret = opts.secret
    if not (bot_id and secret):
        raise ValueError("wecom ws requires bot_id and secret")

    subscribe_id = new_req_id()
    subscribe_frame = build_subscribe(bot_id=bot_id, secret=secret, req_id=subscribe_id)

    stop = asyncio.Event()
    ping_task: Optional[asyncio.Task[None]] = None

    async with websockets.connect(ws_url, ping_interval=None, close_timeout=10) as ws:
        await ws.send(json.dumps(subscribe_frame, ensure_ascii=False))
        raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
        ack = json.loads(raw)
        if not is_subscribe_ok(ack, req_id=subscribe_id):
            raise RuntimeError(f"wecom aibot_subscribe failed: {ack}")
        logger.info("wecom ws subscribed: bot_id=%s", bot_id)
        ping_task = asyncio.create_task(_heartbeat(ws, stop))
        loop = asyncio.get_running_loop()

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=_RECV_TIMEOUT_S)
            except asyncio.TimeoutError:
                logger.debug("wecom ws recv timeout, continue")
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("wecom ws invalid json: %s", raw[:200])
                continue

            cmd = str(msg.get("cmd") or "")
            if cmd == "aibot_msg_callback":
                frame = map_aibot_callback_to_frame(msg)
                req_id = str((msg.get("headers") or {}).get("req_id") or new_req_id())
                stream_id = uuid.uuid4().hex

                def _handle() -> Optional[str]:
                    return connector.handle_frame(frame, send_reply=False)

                try:
                    rendered = await loop.run_in_executor(None, _handle)
                except Exception:
                    logger.exception("wecom handle_frame failed")
                    rendered = "⚠ 抱歉，处理失败，请稍后再试。"
                if not rendered:
                    continue
                await ws.send(
                    json.dumps(
                        build_respond_stream(
                            req_id=req_id,
                            stream_id=stream_id,
                            content=rendered,
                            finish=True,
                        ),
                        ensure_ascii=False,
                    )
                )
            elif cmd == "aibot_event_callback":
                body = msg.get("body") or {}
                if str(body.get("event_type") or body.get("event") or "") in (
                    "enter_chat",
                    "enter_session",
                ):
                    logger.info("wecom enter_chat event: %s", body.get("chatid"))
            elif cmd in ("pong", "ping"):
                continue
            elif int(msg.get("errcode", 0)) != 0:
                logger.warning("wecom ws frame error: %s", msg)


def run_wecom_ws_loop(connector: Any, *, ws_url: str = WECOM_WS_URL) -> None:
    """阻塞运行 WebSocket 事件循环（供 ``WecomAiBotConnector.start`` 调用）。"""
    asyncio.run(_run_wecom_ws_async(connector, ws_url=ws_url))


__all__ = ["run_wecom_ws_loop"]
