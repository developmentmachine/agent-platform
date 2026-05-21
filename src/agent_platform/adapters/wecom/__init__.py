"""企业微信 AiBot connector 骨架。

模块边界（与 ares-agent-pkx 同思路，但完全 Python）：
- ``frame_mapper``       平台 frame → ``PrincipalContext`` + ``conversation_key``
- ``message_normalizer`` 解析消息文本 + 是否 @bot
- ``dedup``              按 msg_id 去重，幂等
- ``stream_reply``       流式回复（增量 patch / 进度文本）
- ``connector``          WebSocket / 回调长连接管理

W1：仅落骨架（类型 + 函数签名 + TODO），不依赖任何具体 WeCom SDK；
后续 commit 接入官方 Python SDK 或自实现 WebSocket。
"""
from agent_platform.adapters.wecom.frame_mapper import map_wecom_frame
from agent_platform.adapters.wecom.message_normalizer import normalize_wecom_text
from agent_platform.adapters.wecom.connector import (
    WecomAiBotConnector,
    WecomAiBotConnectorOptions,
    load_wecom_options_from_env,
)

__all__ = [
    "map_wecom_frame",
    "normalize_wecom_text",
    "WecomAiBotConnector",
    "WecomAiBotConnectorOptions",
    "load_wecom_options_from_env",
]
