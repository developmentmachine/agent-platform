"""agent_platform.core — 平台契约层（无副作用、不依赖任何上层）。

子包：
- ``ports``         端口协议（LLM / MCP Tool / Memory / Repository / Renderer / Guardrail / Push / SessionResolver）
- ``runtime``       运行上下文类型（RunContext / Principal / Session / Budget / ContextVar）
- ``orchestration`` 泛型编排（Phase / Pipeline / RunState 基类 / SideEffectBus / StreamEvent）
- ``registry``      Agent 注册（AgentDefinition / AgentRegistry / entry_points 发现）
- ``errors``        通用异常基类
- ``types``         通用 Pydantic 类型（不含业务）

依赖方向：``core`` 不得 import ``runtime`` / ``infra`` / ``adapters`` / ``agents`` / ``tools_server``。
"""
