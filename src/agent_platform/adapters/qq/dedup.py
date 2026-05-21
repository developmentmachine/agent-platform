"""QQ msg_id 去重 — 与 WeCom 实现共用同一 LRU 结构。"""
from agent_platform.adapters.wecom.dedup import MsgIdDedup

__all__ = ["MsgIdDedup"]
