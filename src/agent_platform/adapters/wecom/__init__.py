"""企业微信适配层。

包含两条通道：
- AiBot 长连接（``connector``）— frame → normalize → dedup → ``AgentRuntime.run``；
- 标准 HTTP 回调（``webhook`` + ``crypto``）— 企微管理后台配置 URL 即可对接，
  与 AiBot 共用同一套 AES + msg_signature 协议。

模块拆分：
- ``crypto``             AES-256-CBC + PKCS7 + msg_signature（W5 新增）；
- ``webhook``            FastAPI router 构造器，自动校验 + 解密 + 派发（W5 新增）；
- ``frame_mapper``       frame → ``PrincipalContext`` + ``conversation_key``；
- ``message_normalizer`` raw text → ``NormalizedMessage``；
- ``dedup``              按 msg_id 去重，幂等；
- ``stream_reply``       2KB-token 阈值的 streaming 缓冲；
- ``connector``          AiBot connector + WS 占位。
"""
from agent_platform.adapters.wecom.connector import (
    WecomAiBotConnector,
    WecomAiBotConnectorOptions,
    load_wecom_options_from_env,
)
from agent_platform.adapters.wecom.crypto import (
    InvalidCorpId,
    InvalidSignature,
    WecomCrypto,
    WecomCryptoError,
)
from agent_platform.adapters.wecom.dedup import MsgIdDedup
from agent_platform.adapters.wecom.frame_mapper import map_wecom_frame
from agent_platform.adapters.wecom.message_normalizer import normalize_wecom_text
from agent_platform.adapters.wecom.webhook import build_wecom_router

__all__ = [
    "InvalidCorpId",
    "InvalidSignature",
    "MsgIdDedup",
    "WecomAiBotConnector",
    "WecomAiBotConnectorOptions",
    "WecomCrypto",
    "WecomCryptoError",
    "build_wecom_router",
    "load_wecom_options_from_env",
    "map_wecom_frame",
    "normalize_wecom_text",
]
