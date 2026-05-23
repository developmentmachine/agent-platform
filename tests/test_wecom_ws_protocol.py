"""企微智能机器人 WebSocket 协议辅助单测。"""
from __future__ import annotations

from agent_platform.adapters.wecom.ws_protocol import (
    build_respond_stream,
    build_subscribe,
    is_subscribe_ok,
    map_aibot_callback_to_frame,
)


def test_build_subscribe_shape() -> None:
    frame = build_subscribe(bot_id="bot1", secret="sec", req_id="rid1")
    assert frame["cmd"] == "aibot_subscribe"
    assert frame["headers"]["req_id"] == "rid1"
    assert frame["body"] == {"bot_id": "bot1", "secret": "sec"}


def test_map_aibot_callback_group_chat() -> None:
    msg = {
        "cmd": "aibot_msg_callback",
        "headers": {"req_id": "req-1"},
        "body": {
            "msgid": "m1",
            "chatid": "c1",
            "chattype": "group",
            "from": {"userid": "u1"},
            "msgtype": "text",
            "text": {"content": "@bot hi"},
        },
    }
    frame = map_aibot_callback_to_frame(msg)
    assert frame["msg_id"] == "m1"
    assert frame["chat_id"] == "c1"
    assert frame["text"]["content"] == "@bot hi"


def test_build_respond_stream_finish() -> None:
    out = build_respond_stream(req_id="r1", stream_id="s1", content="ok", finish=True)
    assert out["cmd"] == "aibot_respond_msg"
    assert out["body"]["stream"]["finish"] is True
    assert out["body"]["stream"]["content"] == "ok"


def test_is_subscribe_ok() -> None:
    assert is_subscribe_ok({"headers": {"req_id": "x"}, "errcode": 0}, req_id="x")
    assert not is_subscribe_ok({"headers": {"req_id": "x"}, "errcode": 1}, req_id="x")
