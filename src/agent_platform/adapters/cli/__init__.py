"""CLI adapter — 按 AgentRegistry 自动发现子命令。

W1：透明 re-export 现有 ``interfaces.cli``；后续 commit 改写为完全基于 registry 的
动态子命令分发（替换 AGENTS 硬编码字典）。
"""
from agent_platform.interfaces.cli import cli_main

__all__ = ["cli_main"]
