"""WeCom / QQ adapter 归一化与去重的最小行为测试。

这些测试**不依赖任何 SDK**，只验证 frame → AdapterContext 的纯函数行为。
"""
from __future__ import annotations

from agent_platform.adapters import build_conversation_key
from agent_platform.adapters.wecom import map_wecom_frame, normalize_wecom_text
from agent_platform.adapters.wecom.dedup import MsgIdDedup
from agent_platform.adapters.qq import (
    map_qq_c2c_message,
    map_qq_group_message,
    normalize_qq_text,
)
from agent_platform.adapters.qq.ws_auth import build_ws_identify_token, parse_qq_ws_auth_mode


def test_build_conversation_key_skips_empty_parts():
    assert build_conversation_key("wecom", "peer", "user") == "wecom:peer:user"
    assert build_conversation_key("qq", "", "user") == "qq:user"


def test_map_wecom_frame_basic():
    p, key = map_wecom_frame({"from": {"userid": "alice"}, "chat_id": "grp01"})
    assert p.subject == "alice"
    assert p.source == "wecom"
    assert key == "wecom:grp01:alice"


def test_normalize_wecom_text_strips_at_prefix():
    msg = normalize_wecom_text({"text": {"content": "@bot 你好"}}, bot_name="bot")
    assert msg.is_at_bot is True
    assert msg.text == "你好"


def test_msg_id_dedup_lru():
    d = MsgIdDedup(capacity=2)
    assert d.seen("a") is False
    assert d.seen("a") is True
    assert d.seen("b") is False
    assert d.seen("c") is False
    # capacity=2，"a" 应已被淘汰
    assert d.seen("a") is False


def test_map_qq_group_message_builds_conversation_key():
    p, key = map_qq_group_message(
        {"group_openid": "g1", "author": {"member_openid": "u1"}}
    )
    assert p.subject == "u1"
    assert p.source == "qq_group"
    assert key == "qq:group:g1:u1"


def test_map_qq_c2c_message_builds_conversation_key():
    p, key = map_qq_c2c_message({"author": {"user_openid": "u1"}})
    assert p.subject == "u1"
    assert p.source == "qq_c2c"
    assert key == "qq:c2c:u1"


def test_normalize_qq_text_strips_at_mention():
    msg = normalize_qq_text({"content": "<@!123> hello"}, bot_user_id="123")
    assert msg.is_at_bot is True
    assert msg.text == "hello"


def test_parse_qq_ws_auth_mode():
    assert parse_qq_ws_auth_mode(None) == "app_token"
    assert parse_qq_ws_auth_mode("bot") == "bot_token"
    assert parse_qq_ws_auth_mode("APP_TOKEN") == "app_token"


def test_build_ws_identify_token_format():
    bot = build_ws_identify_token(app_id="123", app_secret="x", mode="bot_token")
    app = build_ws_identify_token(app_id="123", app_secret="x", mode="app_token")
    assert bot.startswith("Bot ")
    assert app.startswith("QQBot ")
