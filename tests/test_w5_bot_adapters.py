"""W5: QQ botpy 适配 + 企微 crypto / webhook 主路径可调用性。"""
from __future__ import annotations

import base64
import os
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ─── WeCom crypto: encrypt → decrypt 自洽 + signature 校验 ────────────────────


@pytest.fixture
def crypto():
    from agent_platform.adapters.wecom.crypto import WecomCrypto

    # 43 字符 EncodingAESKey（base64 不带尾部 "="；解码后 32 字节）
    aes_key = base64.b64encode(os.urandom(32)).decode("utf-8")[:43]
    return WecomCrypto(
        token="test-token",
        encoding_aes_key=aes_key,
        corp_id="wx_test_corp",
    )


def test_crypto_round_trip(crypto) -> None:
    msg = "<xml><Content>你好 Bot</Content></xml>"
    enc = crypto.encrypt(msg)
    plain, decoded_corp_id = crypto.decrypt(enc)
    assert plain == msg
    assert decoded_corp_id == "wx_test_corp"


def test_crypto_signature_verify_ok_and_fail(crypto) -> None:
    from agent_platform.adapters.wecom.crypto import InvalidSignature

    enc = "anyciphertext"
    timestamp = "1700000000"
    nonce = "abc"
    sig = crypto.sign(timestamp, nonce, enc)
    crypto.verify_signature(sig, timestamp, nonce, enc)  # 不抛
    with pytest.raises(InvalidSignature):
        crypto.verify_signature("wrong-sig", timestamp, nonce, enc)


def test_crypto_decrypt_rejects_wrong_corp_id(crypto) -> None:
    from agent_platform.adapters.wecom.crypto import InvalidCorpId, WecomCrypto

    enc = crypto.encrypt("hello")
    # 用同 key 但不同 corp_id 的 crypto 解密 → 抛 InvalidCorpId
    other = WecomCrypto(
        token=crypto.token,
        encoding_aes_key=crypto.encoding_aes_key,
        corp_id="wx_other_corp",
    )
    with pytest.raises(InvalidCorpId):
        other.decrypt(enc)


# ─── WeCom webhook: GET verify_url + POST receive ────────────────────────────


def _build_test_app(crypto, handler) -> TestClient:
    from agent_platform.adapters.wecom.webhook import build_wecom_router

    app = FastAPI()
    app.include_router(build_wecom_router(crypto, handler))
    return TestClient(app)


def test_wecom_webhook_verify_url_returns_echostr(crypto) -> None:
    echostr_plain = "echo-content"
    encrypted = crypto.encrypt(echostr_plain)
    timestamp = "1700000001"
    nonce = "n1"
    sig = crypto.sign(timestamp, nonce, encrypted)

    client = _build_test_app(crypto, lambda frame: None)
    r = client.get(
        "/v1/adapters/wecom/callback",
        params={"msg_signature": sig, "timestamp": timestamp, "nonce": nonce, "echostr": encrypted},
    )
    assert r.status_code == 200
    assert r.text == echostr_plain


def test_wecom_webhook_verify_url_rejects_bad_signature(crypto) -> None:
    encrypted = crypto.encrypt("anything")
    client = _build_test_app(crypto, lambda frame: None)
    r = client.get(
        "/v1/adapters/wecom/callback",
        params={"msg_signature": "bad", "timestamp": "1", "nonce": "n", "echostr": encrypted},
    )
    assert r.status_code == 403


def test_wecom_webhook_post_dispatches_decrypted_frame(crypto) -> None:
    inner_xml = (
        "<xml><ToUserName>wx_test_corp</ToUserName>"
        "<FromUserName>user-1</FromUserName>"
        "<MsgType>text</MsgType><Content>你好</Content>"
        "<MsgId>m-1</MsgId></xml>"
    )
    encrypted = crypto.encrypt(inner_xml)
    timestamp = "1700000099"
    nonce = "n2"
    sig = crypto.sign(timestamp, nonce, encrypted)

    received: List[Dict[str, Any]] = []

    def _handler(frame):
        received.append(frame)
        return None

    client = _build_test_app(crypto, _handler)
    envelope_xml = f"<xml><Encrypt><![CDATA[{encrypted}]]></Encrypt></xml>"
    r = client.post(
        "/v1/adapters/wecom/callback",
        params={"msg_signature": sig, "timestamp": timestamp, "nonce": nonce},
        content=envelope_xml,
        headers={"Content-Type": "application/xml"},
    )
    assert r.status_code == 200
    assert received and received[0].get("Content") == "你好"
    assert received[0].get("FromUserName") == "user-1"


# ─── QQ botpy adapter: 事件桥接 → connector ──────────────────────────────────


def test_botpy_frame_mappers_extract_essentials() -> None:
    from agent_platform.adapters.qq.botpy_client import (
        _frame_from_c2c_message,
        _frame_from_group_message,
    )

    class _Author:
        id = "u123"
        user_openid = "ou123"

    class _GroupMsg:
        id = "m-g"
        content = "@bot 你好"
        group_openid = "g-1"
        author = _Author()

    class _C2CMsg:
        id = "m-c"
        content = "策略"
        author = _Author()

    gframe = _frame_from_group_message(_GroupMsg())
    assert gframe["id"] == "m-g" and gframe["group_openid"] == "g-1"
    assert gframe["author"]["id"] == "u123"

    cframe = _frame_from_c2c_message(_C2CMsg())
    assert cframe["id"] == "m-c"
    assert cframe["author"]["id"] == "ou123"


def test_build_botpy_client_dispatches_to_connector(monkeypatch: pytest.MonkeyPatch) -> None:
    """模拟 botpy.Client：验证事件桥接调到 connector handler。"""
    import botpy
    from agent_platform.adapters.qq import botpy_client as bc_mod

    # 用一个 FakeClient 取代 botpy.Client，避免实例化时建事件循环
    instances: List[Any] = []

    class _FakeClient:
        def __init__(self, intents):
            instances.append(self)
            self.intents = intents

    monkeypatch.setattr(botpy, "Client", _FakeClient)

    dispatched: List[str] = []

    class _FakeConnector:
        def handle_group_message(self, frame):
            dispatched.append(f"group:{frame.get('id')}")
            return None

        def handle_c2c_message(self, frame):
            dispatched.append(f"c2c:{frame.get('id')}")
            return None

    client = bc_mod.build_botpy_client(_FakeConnector())
    assert instances and client is instances[0]
    # FakeClient 没有 on_* 方法（即子类 _PlatformBotpyClient 应继承自 FakeClient
    # 并添加这些方法）。手动 await 一下子类方法验证桥接。
    import asyncio

    class _Msg:
        id = "x1"
        content = "hi"
        group_openid = "g"
        author = type("A", (), {"id": "u", "user_openid": "ou"})()
        channel_id = None
        guild_id = None

        replies: list[str] = []

        async def reply(self, content, msg_seq=1):
            replies.append(content)
            dispatched.append(f"reply:{content}")

    asyncio.run(client.on_group_at_message_create(_Msg()))
    asyncio.run(client.on_c2c_message_create(_Msg()))
    assert "group:x1" in dispatched
    assert "c2c:x1" in dispatched


def test_qq_chunked_reply_sends_multiple_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_platform.adapters.qq import botpy_client as bc_mod

    sent: list[tuple[str, int | None]] = []

    class _Msg:
        id = "m1"
        group_openid = "g1"
        author = type("A", (), {"user_openid": None})()
        _api = type(
            "API",
            (),
            {
                "post_group_message": lambda *a, **k: sent.append(("active", k.get("content", ""))),
            },
        )()

        async def reply(self, content, msg_seq=1):
            sent.append(("passive", content, msg_seq))

    import asyncio

    long_text = "段\n\n" + ("复" * 1200) + "\n\n尾"
    chunks = __import__(
        "agent_platform.adapters.reply_chunks", fromlist=["split_reply_chunks"]
    ).split_reply_chunks(long_text, max_chars=400)
    asyncio.run(bc_mod._send_chunked_reply(_Msg(), chunks))
    assert len(sent) >= 2
    passive = [s for s in sent if s[0] == "passive"]
    assert passive[0][2] == 1
    assert passive[-1][2] <= 5


# ─── connector.start() 早退路径：未配置时不应 crash ──────────────────────────


def test_load_qq_options_accepts_client_secret() -> None:
    from agent_platform.adapters.qq.connector import load_qq_options_from_env

    opts = load_qq_options_from_env(
        {
            "QQ_BOT_APP_ID": "1904044228",
            "QQ_BOT_CLIENT_SECRET": "secret-value",
            "QQ_BOT_ENABLED": "true",
        }
    )
    assert opts.app_id == "1904044228"
    assert opts.app_secret == "secret-value"


def test_qq_connector_start_noop_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_platform.adapters.qq.connector import (
        QqBotConnector,
        QqBotConnectorOptions,
    )

    class _NoopRuntime:
        pass

    opts = QqBotConnectorOptions(app_id=None, app_secret=None, enabled=True)
    QqBotConnector(options=opts, runtime=_NoopRuntime()).start()  # 不应抛


def test_wecom_connector_start_noop_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_platform.adapters.wecom.connector import (
        WecomAiBotConnector,
        WecomAiBotConnectorOptions,
    )

    class _NoopRuntime:
        pass

    opts = WecomAiBotConnectorOptions(bot_id=None, secret=None, enabled=True)
    WecomAiBotConnector(options=opts, runtime=_NoopRuntime()).start()  # 不应抛
