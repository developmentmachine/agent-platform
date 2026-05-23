"""McpToolGateway — 平台统一的工具治理 + 调度门面。

职责（与原 ``infrastructure.tools.runner.RecapToolRunner`` 一致，但**与具体 Agent 解耦**）：
1. ``openai_compatible_schemas``  → 由 ``McpClientPort.list_tools`` 推导（不再硬编码）；
2. ``execute(name, arguments)``    → 走 ``McpClientPort.call``，叠加：
   - ToolPolicy（enabled / required_role / per-tool budget / timeout）
   - 全局 ``AgentBudget``（tool_calls 维度）
   - ``tool_invocations`` 审计落库 + ``record_tool_invocation`` 指标
3. ``prefetch_for_prompt(date)``   → 对预取场景批量调用，与单次 execute 同治理。

设计原则：
- 该 gateway 由 Composition Root 装配并通过 ContextVar / 依赖注入下发；
- 不依赖任何 Agent；任何 Agent 都能复用。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from agent_platform.config.settings import Settings
from agent_platform.core.ports.mcp_tool import McpClientPort, McpToolDescriptor
from agent_platform.core.runtime.contextvars import current_budget, current_run_context
from agent_platform.infra.guardrail.tools import (
    ToolBudgetExceeded,
    ToolDisabled,
    ToolForbidden,
    ToolNotRegistered,
    ToolPolicy,
    ToolPolicyError,
    ToolPolicyRegistry,
    ToolTimeout,
    build_default_registry,
)

logger = logging.getLogger("agent_platform.runtime.mcp_gateway")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# Settings 中的「工具开关」与工具名映射（沿用历史命名）。
_SETTINGS_TOOL_FLAGS: Dict[str, str] = {
    "web_search": "tools_web_search",
    "query_market_data": "tools_market_data",
    "query_history": "tools_history",
}


def _resolve_principal_role(settings: Settings) -> str:
    """优先使用 ``current_principal.role``（W1 新增）；其次 ``domain.principal``；
    最后回落 ``Settings.principal_role``，与历史行为一致。"""
    try:
        from agent_platform.core.runtime.contextvars import current_principal

        principal = current_principal.get()
        if principal is not None and (principal.role or "").strip():
            return principal.role
    except Exception:
        pass
    try:
        from agent_platform.domain.principal import get_principal

        role = (get_principal().role or "").strip()
        if role:
            return role
    except Exception:
        pass
    return settings.principal_role


def _resolve_tenant_id() -> Optional[str]:
    try:
        from agent_platform.core.runtime.contextvars import current_principal

        principal = current_principal.get()
        if principal is not None and principal.tenant_id:
            return principal.tenant_id
    except Exception:
        pass
    try:
        from agent_platform.domain.principal import get_principal

        tid = get_principal().tenant_id
        if tid:
            return tid
    except Exception:
        pass
    ctx = current_run_context.get()
    if ctx is not None:
        return getattr(ctx, "tenant_id", None)
    return None


class McpToolGateway:
    """工具治理 + 调度门面：上层只需要 schemas / execute / prefetch 三件事。"""

    __slots__ = ("_settings", "_client", "_policy_registry", "_per_tool_used", "_descriptors_cache")

    def __init__(
        self,
        settings: Settings,
        client: McpClientPort,
        *,
        policy_registry: Optional[ToolPolicyRegistry] = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._policy_registry = policy_registry or build_default_registry()
        self._per_tool_used: Dict[str, int] = {}
        self._descriptors_cache: Optional[List[McpToolDescriptor]] = None

    # ─── 元信息 ───────────────────────────────────────────────────────────

    @property
    def client(self) -> McpClientPort:
        return self._client

    @property
    def policy_registry(self) -> ToolPolicyRegistry:
        return self._policy_registry

    @property
    def tools_enabled(self) -> bool:
        return bool(self._settings.tools_enabled)

    def _list_descriptors_sync(self) -> List[McpToolDescriptor]:
        if self._descriptors_cache is not None:
            return self._descriptors_cache
        # 提供同步入口以适配现有调用方（providers / runner）。
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._descriptors_cache = asyncio.run(self._client.list_tools())
        else:
            # 已在事件循环里 — 用子线程
            import threading

            box: Dict[str, List[McpToolDescriptor]] = {}

            def _runner() -> None:
                box["v"] = asyncio.run(self._client.list_tools())

            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            t.join()
            self._descriptors_cache = box["v"]
        return self._descriptors_cache

    def _settings_flag_on(self, name: str) -> bool:
        flag = _SETTINGS_TOOL_FLAGS.get(name)
        if flag is None:
            return True
        return bool(getattr(self._settings, flag, False))

    def enabled_tool_names(self) -> Set[str]:
        """允许条件 = 总开关 ∩ Settings.tools_* ∩ ToolPolicy.enabled ∩ 角色满足。"""
        if not self._settings.tools_enabled:
            return set()
        principal = _resolve_principal_role(self._settings)
        descriptors = {d.name for d in self._list_descriptors_sync()}
        names: Set[str] = set()
        for name in self._policy_registry.names():
            if name not in descriptors:
                # Policy 注册了但 MCP server 不提供 — 静默跳过（不抛 ToolNotRegistered）
                continue
            if not self._settings_flag_on(name):
                continue
            policy = self._policy_registry.get(name)
            if policy is None or not policy.enabled:
                continue
            if not policy.is_role_allowed(principal):
                continue
            names.add(name)
        return names

    def openai_compatible_schemas(self) -> List[Dict[str, Any]]:
        allowed = self.enabled_tool_names()
        if not allowed:
            return []
        out: List[Dict[str, Any]] = []
        for desc in self._list_descriptors_sync():
            if desc.name not in allowed:
                continue
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": desc.name,
                        "description": desc.description,
                        "parameters": desc.input_schema,
                    },
                }
            )
        return out

    # ─── 单次执行 ─────────────────────────────────────────────────────────

    def execute(self, name: str, arguments: Dict[str, Any], db_path: Optional[str] = None) -> str:
        """同步执行：policy + budget + audit + timeout，全部沿用历史语义。

        ``db_path`` 参数保留只为旧调用方向后兼容；handler 自行从环境变量解析。
        """
        principal = _resolve_principal_role(self._settings)
        tenant_id = _resolve_tenant_id()
        ctx = current_run_context.get()
        request_id = ctx.request_id if ctx is not None else None

        # 1) policy 注册检查
        try:
            policy = self._policy_registry.require(name)
        except ToolNotRegistered as e:
            self._audit(
                request_id=request_id,
                tool_name=name,
                status="denied",
                read_only=True,
                principal_role=principal,
                tenant_id=tenant_id,
                arguments=arguments,
                latency_ms=0,
                error=str(e),
            )
            raise

        # 2) policy.enabled / Settings.tools_*
        if not policy.enabled or not self._settings_flag_on(name) or not self._settings.tools_enabled:
            err = ToolDisabled(f"tool '{name}' is disabled by policy or settings")
            self._audit(
                request_id=request_id,
                tool_name=name,
                status="denied",
                read_only=policy.read_only,
                principal_role=principal,
                tenant_id=tenant_id,
                arguments=arguments,
                latency_ms=0,
                error=str(err),
            )
            raise err

        # 3) 角色
        if not policy.is_role_allowed(principal):
            err = ToolForbidden(
                f"tool '{name}' requires role '{policy.required_role}', "
                f"current principal_role='{principal}'"
            )
            self._audit(
                request_id=request_id,
                tool_name=name,
                status="denied",
                read_only=policy.read_only,
                principal_role=principal,
                tenant_id=tenant_id,
                arguments=arguments,
                latency_ms=0,
                error=str(err),
            )
            raise err

        # 4) per-tool budget
        if policy.max_calls_per_run > 0:
            used = self._per_tool_used.get(name, 0)
            if used + 1 > policy.max_calls_per_run:
                err = ToolBudgetExceeded(name, policy.max_calls_per_run, used + 1)
                self._audit(
                    request_id=request_id,
                    tool_name=name,
                    status="denied",
                    read_only=policy.read_only,
                    principal_role=principal,
                    tenant_id=tenant_id,
                    arguments=arguments,
                    latency_ms=0,
                    error=str(err),
                )
                raise err

        # 5) 全局 AgentBudget
        budget = current_budget.get()
        if budget is not None:
            try:
                budget.record_tool_call()
            except Exception as e:
                self._audit(
                    request_id=request_id,
                    tool_name=name,
                    status="denied",
                    read_only=policy.read_only,
                    principal_role=principal,
                    tenant_id=tenant_id,
                    arguments=arguments,
                    latency_ms=0,
                    error=f"agent_budget: {e}",
                )
                raise

        # 6) 真正调用 MCP client
        self._per_tool_used[name] = self._per_tool_used.get(name, 0) + 1
        t0 = time.monotonic()
        timeout_s = float(policy.timeout_s) if policy.timeout_s and policy.timeout_s > 0 else None
        try:
            result = self._call_sync(name, arguments, timeout_s=timeout_s)
        except Exception as e:
            self._audit(
                request_id=request_id,
                tool_name=name,
                status="failed",
                read_only=policy.read_only,
                principal_role=principal,
                tenant_id=tenant_id,
                arguments=arguments,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error=str(e)[:500],
            )
            raise

        latency_ms = int((time.monotonic() - t0) * 1000)

        # MCP client 把 timeout 转成 is_error；翻译回 ``ToolTimeout`` 与历史一致
        if result.is_error and result.meta.get("error_kind") == "timeout":
            err_t = ToolTimeout(name, policy.timeout_s)
            self._audit(
                request_id=request_id,
                tool_name=name,
                status="timeout",
                read_only=policy.read_only,
                principal_role=principal,
                tenant_id=tenant_id,
                arguments=arguments,
                latency_ms=latency_ms,
                error=str(err_t),
            )
            raise err_t

        if result.is_error:
            self._audit(
                request_id=request_id,
                tool_name=name,
                status="failed",
                read_only=policy.read_only,
                principal_role=principal,
                tenant_id=tenant_id,
                arguments=arguments,
                latency_ms=latency_ms,
                error=(result.content or "")[:500],
            )
            return result.content or ""

        self._audit(
            request_id=request_id,
            tool_name=name,
            status="ok",
            read_only=policy.read_only,
            principal_role=principal,
            tenant_id=tenant_id,
            arguments=arguments,
            latency_ms=latency_ms,
            error=None,
        )
        return result.content or ""

    def _call_sync(self, name: str, arguments: Dict[str, Any], *, timeout_s: Optional[float]):
        # 借用 InProcessMcpClient.call_sync 的同步入口（任何 McpClientPort 实现都可走 asyncio）
        client = self._client
        call_sync = getattr(client, "call_sync", None)
        if callable(call_sync):
            return call_sync(name, arguments, timeout_s=timeout_s)
        # 通用回退：临时新线程跑 asyncio
        import threading

        box: Dict[str, Any] = {}

        def _runner() -> None:
            box["v"] = asyncio.run(
                client.call(name, arguments, timeout_s=timeout_s)
            )

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join()
        return box["v"]

    # ─── 预取 ─────────────────────────────────────────────────────────────

    def prefetch_for_prompt(self, date: str, db_path: Optional[str] = None) -> str:
        """对启用工具批量预取，统一治理。"""
        allowed = self.enabled_tool_names()
        if not allowed:
            return ""

        principal = _resolve_principal_role(self._settings)
        tenant_id = _resolve_tenant_id()
        ctx = current_run_context.get()
        request_id = ctx.request_id if ctx is not None else None
        budget = current_budget.get()

        # 与原 RecapToolRunner.prefetch 完全一致的查询入参
        prefetch_args: Dict[str, List[Dict[str, Any]]] = {
            "web_search": [{"query": f"A股行情 {date} 上证指数 北向资金 板块"}],
            "query_market_data": [
                {"data_type": "index", "date": date},
                {"data_type": "sector", "date": date},
                {"data_type": "northbound", "date": date},
            ],
            "query_history": [{"mode": "daily", "limit": 3}],
        }

        actually_used: Set[str] = set()
        for name in allowed:
            policy = self._policy_registry.get(name)
            if policy is None:
                continue
            if policy.max_calls_per_run > 0:
                used = self._per_tool_used.get(name, 0)
                if used + 1 > policy.max_calls_per_run:
                    self._audit(
                        request_id=request_id,
                        tool_name=name,
                        status="denied",
                        read_only=policy.read_only,
                        principal_role=principal,
                        tenant_id=tenant_id,
                        arguments={"phase": "prefetch", "date": date},
                        latency_ms=0,
                        error=f"per_tool_budget: limit={policy.max_calls_per_run}",
                    )
                    continue
            self._per_tool_used[name] = self._per_tool_used.get(name, 0) + 1
            actually_used.add(name)

        if not actually_used:
            return ""
        if budget is not None:
            budget.record_tool_call(n=len(actually_used))

        t0 = time.monotonic()
        parts: List[str] = []
        try:
            if "web_search" in actually_used:
                for args in prefetch_args["web_search"]:
                    parts.append(
                        f"【联网搜索结果】\n{self._call_sync('web_search', args, timeout_s=None).content}"
                    )
            if "query_market_data" in actually_used:
                for args in prefetch_args["query_market_data"]:
                    parts.append(
                        f"【{args['data_type']} 行情数据】\n"
                        f"{self._call_sync('query_market_data', args, timeout_s=None).content}"
                    )
            if "query_history" in actually_used:
                for args in prefetch_args["query_history"]:
                    parts.append(
                        f"【近期历史复盘】\n{self._call_sync('query_history', args, timeout_s=None).content}"
                    )
        except Exception as e:
            for name in actually_used:
                self._audit(
                    request_id=request_id,
                    tool_name=name,
                    status="failed",
                    read_only=True,
                    principal_role=principal,
                    tenant_id=tenant_id,
                    arguments={"phase": "prefetch", "date": date},
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    error=str(e)[:500],
                )
            raise

        elapsed_each = int(((time.monotonic() - t0) * 1000) / max(1, len(actually_used)))
        for name in actually_used:
            self._audit(
                request_id=request_id,
                tool_name=name,
                status="ok",
                read_only=True,
                principal_role=principal,
                tenant_id=tenant_id,
                arguments={"phase": "prefetch", "date": date},
                latency_ms=elapsed_each,
                error=None,
            )
        return "\n\n".join(parts)

    # ─── 审计 ─────────────────────────────────────────────────────────────

    def _audit(
        self,
        *,
        request_id: Optional[str],
        tool_name: str,
        status: str,
        read_only: bool,
        principal_role: Optional[str],
        arguments: Optional[Dict[str, Any]],
        latency_ms: Optional[int],
        error: Optional[str],
        tenant_id: Optional[str] = None,
    ) -> None:
        from agent_platform.runtime.observability.metrics import record_tool_invocation

        record_tool_invocation(tool_name, status)
        if not self._settings.tool_audit_enabled:
            return
        try:
            from agent_platform.infra.persistence.db import insert_tool_invocation

            insert_tool_invocation(
                self._settings.db_path,
                request_id=request_id,
                tool_name=tool_name,
                status=status,
                read_only=read_only,
                principal_role=principal_role,
                arguments=arguments,
                latency_ms=latency_ms,
                error=error,
                created_at=_utc_now_iso(),
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.warning(
                _stable_json(
                    {
                        "event": "tool_audit_write_failed",
                        "tool": tool_name,
                        "status": status,
                        "error": str(e),
                    }
                )
            )


__all__ = [
    "McpToolGateway",
    "ToolBudgetExceeded",
    "ToolDisabled",
    "ToolForbidden",
    "ToolNotRegistered",
    "ToolPolicyError",
    "ToolTimeout",
]
