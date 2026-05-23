"""企业微信智能机器人 WebSocket 长连接协议辅助（文档 path/101463）。"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

WECOM_WS_URL = "wss://openws.work.weixin.qq.com"


def new_req_id() -> str:
    return uuid.uuid4().hex


def build_subscribe(*, bot_id: str, secret: str, req_id: Optional[str] = None) -> Dict[str, Any]:
    rid = req_id or new_req_id()
    return {
        "cmd": "aibot_subscribe",
        "headers": {"req_id": rid},
        "body": {"bot_id": bot_id, "secret": secret},
    }


def build_ping(*, req_id: Optional[str] = None) -> Dict[str, Any]:
    return {"cmd": "ping", "headers": {"req_id": req_id or new_req_id()}}


def build_respond_stream(
    *,
    req_id: str,
    stream_id: str,
    content: str,
    finish: bool = True,
) -> Dict[str, Any]:
    return {
        "cmd": "aibot_respond_msg",
        "headers": {"req_id": req_id},
        "body": {
            "msgtype": "stream",
            "stream": {
                "id": stream_id,
                "finish": finish,
                "content": content,
            },
        },
    }


def map_aibot_callback_to_frame(msg: Dict[str, Any]) -> Dict[str, Any]:
    """把 ``aibot_msg_callback`` 转为 ``WecomAiBotConnector.handle_frame`` 期望的 frame。"""
    body = msg.get("body") or {}
    chattype = str(body.get("chattype") or "")
    from_user = body.get("from") if isinstance(body.get("from"), dict) else {}
    text_body = body.get("text") if isinstance(body.get("text"), dict) else {}
    frame: Dict[str, Any] = {
        "msg_id": body.get("msgid"),
        "message_id": body.get("msgid"),
        "from": from_user,
        "text": text_body,
        "msgtype": body.get("msgtype"),
        "chattype": chattype,
        "_ws_raw": msg,
    }
    if chattype == "group":
        frame["chat_id"] = body.get("chatid")
    else:
        frame["from_user_id"] = from_user.get("userid")
    return frame


def is_subscribe_ok(msg: Dict[str, Any], *, req_id: str) -> bool:
    headers = msg.get("headers") or {}
    return headers.get("req_id") == req_id and int(msg.get("errcode", -1)) == 0


__all__ = [
    "WECOM_WS_URL",
    "build_ping",
    "build_respond_stream",
    "build_subscribe",
    "is_subscribe_ok",
    "map_aibot_callback_to_frame",
    "new_req_id",
]
