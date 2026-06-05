"""shim → agent_platform.infra.llm.parse

LLM 输出解析 + schema 校验的规范位置已迁移到 infra/llm/parse.py。
本文件保留向后兼容，新代码请直接 import agent_platform.infra.llm.parse。
"""
from agent_platform.infra.llm.parse import (  # noqa: F401
    _stable_json,
    parse_and_validate,
    parse_json_from_text,
)

__all__ = ["_stable_json", "parse_and_validate", "parse_json_from_text"]
