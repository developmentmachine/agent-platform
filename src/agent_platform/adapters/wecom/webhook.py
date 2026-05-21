"""企业微信回调 FastAPI 路由 (W5)。

URL 形式：``/v1/adapters/wecom/callback``

- ``GET``  企业微信「URL 验证」流程：解密 echostr 原样回写；
- ``POST`` 接收加密 XML，AES 解密后转 ``WecomAiBotConnector.handle_frame``，
  并以 ``application/xml`` 返回加密后的应答（如有）。

把它作为 ``http_router_factory`` 挂到 ``WecomAdapterDefinition``（W6 注册），
也可以让任意 Agent 直接复用。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response

from agent_platform.adapters.wecom.crypto import (
    InvalidCorpId,
    InvalidSignature,
    WecomCrypto,
    WecomCryptoError,
)

logger = logging.getLogger("agent_platform.adapters.wecom.webhook")


def _parse_xml(xml_text: str) -> Dict[str, str]:
    """非常薄的 XML 解析（仅取 ``<tag>...</tag>`` 形式）。

    避免引入 ``defusedxml`` 等额外依赖；企业微信回调结构固定，足够用。
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)
    return {child.tag: (child.text or "") for child in root}


def _extract_encrypted(xml_text: str) -> str:
    parts = _parse_xml(xml_text)
    return parts.get("Encrypt", "")


def build_wecom_router(
    crypto: WecomCrypto,
    handler: Callable[[Dict[str, Any]], Optional[str]],
    *,
    path: str = "/v1/adapters/wecom/callback",
    tags: Optional[list] = None,
) -> APIRouter:
    """组装企业微信回调 router。

    Args:
        crypto: 加解密器（token / encoding_aes_key / corp_id）
        handler: 业务层 frame handler，签名 ``(frame: dict) -> Optional[reply_xml]``；
                 通常传入 ``WecomAiBotConnector.handle_frame``
    """
    router = APIRouter(tags=tags or ["wecom"])

    @router.get(path)
    def verify_url(
        msg_signature: str = Query(...),
        timestamp: str = Query(...),
        nonce: str = Query(...),
        echostr: str = Query(...),
    ) -> Response:
        try:
            crypto.verify_signature(msg_signature, timestamp, nonce, echostr)
            plain, _ = crypto.decrypt(echostr)
        except InvalidSignature as e:
            logger.warning("wecom verify_url signature invalid: %s", e)
            raise HTTPException(status_code=403, detail="invalid signature")
        except (InvalidCorpId, WecomCryptoError) as e:
            logger.warning("wecom verify_url decrypt failed: %s", e)
            raise HTTPException(status_code=400, detail="decrypt failed")
        return Response(content=plain, media_type="text/plain")

    @router.post(path)
    async def receive(
        request: Request,
        msg_signature: str = Query(...),
        timestamp: str = Query(...),
        nonce: str = Query(...),
    ) -> Response:
        body = (await request.body()).decode("utf-8")
        encrypted = _extract_encrypted(body)
        try:
            crypto.verify_signature(msg_signature, timestamp, nonce, encrypted)
            plain, _ = crypto.decrypt(encrypted)
        except InvalidSignature as e:
            logger.warning("wecom receive signature invalid: %s", e)
            raise HTTPException(status_code=403, detail="invalid signature")
        except (InvalidCorpId, WecomCryptoError) as e:
            logger.warning("wecom receive decrypt failed: %s", e)
            raise HTTPException(status_code=400, detail="decrypt failed")

        frame = _parse_xml(plain)
        try:
            reply = handler(frame)
        except Exception:
            logger.exception("wecom handler error")
            return Response(status_code=200)

        if not reply:
            return Response(status_code=200)
        # 应答需要再加密；这里仅返回原文，便于上层自行选择是否加密回包
        return Response(content=reply, media_type="application/xml")

    return router


__all__ = ["build_wecom_router"]
