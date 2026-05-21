"""平台级异常基类（与现有 domain.models 中的具体业务异常并存）。

业务异常（如 ``LlmBusinessError`` / ``LlmBudgetExceeded``）继续放在原位置以保兼容；
本文件只放跨 Agent / 跨入口的平台基类。
"""
from __future__ import annotations


class PlatformError(Exception):
    """平台基类异常。"""


class AgentNotFound(PlatformError):
    """注册表中找不到指定 agent_id。"""


class PipelinePhaseError(PlatformError):
    """Phase 执行内出现的预期内异常（与 transport 错误区分）。"""


class ToolGatewayError(PlatformError):
    """McpToolGateway 治理层拒绝（白名单 / 角色 / 预算 / 超时等）。"""
