"""QQ Bot connector 骨架。

模块边界（与 ares-agent-pkx 同思路）：
- ``frame_mapper``       群消息 / C2C → ``PrincipalContext`` + ``conversation_key``
- ``message_normalizer`` 文本抽取 / @bot 判定
- ``dedup``              基于 msg_id 去重
- ``ws_auth``            WebSocket Identify token
- ``connector``          长连接管理

W1：仅落骨架；后续 commit 接入 ``botpy`` 或自实现 WS。
"""
from agent_platform.adapters.qq.frame_mapper import map_qq_group_message, map_qq_c2c_message
from agent_platform.adapters.qq.message_normalizer import normalize_qq_text
from agent_platform.adapters.qq.connector import (
    QqBotConnector,
    QqBotConnectorOptions,
    load_qq_options_from_env,
)

__all__ = [
    "map_qq_group_message",
    "map_qq_c2c_message",
    "normalize_qq_text",
    "QqBotConnector",
    "QqBotConnectorOptions",
    "load_qq_options_from_env",
]
