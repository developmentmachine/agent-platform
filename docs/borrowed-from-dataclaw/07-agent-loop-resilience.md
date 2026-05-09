# 07 · Agent Loop 韧性

> **状态**：agent-platform 的 `application/agent.py` 是"单次请求 → 单次完整 pipeline"的 batch agent，目前还没有典型 chat agent 那种"多轮工具循环"的韧性细节。如果未来扩到 multi-turn / interactive 模式（IM 接入、长会话），下面这些坑都会踩到。

DataClaw 在 `src/services/agentLoop.ts` 1000+ 行里沉淀了一组**实战中调出来**的韧性策略。我们挑出最关键的 5 条沉淀进来。

## 1. Dangling Tool Call 修复

### 1.1 问题

OpenAI / Anthropic 的工具循环要求：每个 `assistant.tool_calls` 必须紧跟所有对应 `tool` 角色的 response 才能再发下一个请求。

**进程崩溃 / 写库失败 / 用户中断** 等场景下，会出现"assistant 消息已 append 到 session_messages，但 tool response 没全部写入"——再下次加载历史，OpenAI API 直接 400。

### 1.2 DataClaw 做法

```ts
function repairDanglingToolCalls(messages): ChatCompletionMessageParam[] {
  // 遍历 assistant 消息：
  // - 收集它的 tool_call_ids 集合
  // - 看后续连续 tool messages 的 tool_call_id
  // - 若有缺失 → 把这条 assistant 的 tool_calls 字段去掉，并把后面那串"半截 tool 块"丢弃
  //   并把 content 替换为 "(tool execution interrupted)"
}
```

历史窗口截断时也可能把开头切到一段 tool 消息的中间，需要 `while trimmed[0].role === 'tool': trimmed = trimmed[1:]`。

### 1.3 Python 等价骨架

```python
# src/agent_platform/application/orchestration/history_repair.py
from __future__ import annotations
from typing import Iterable

def repair_dangling_tool_calls(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") != "assistant":
            out.append(msg)
            i += 1
            continue

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            out.append(msg)
            i += 1
            continue

        expected_ids = {tc["id"] for tc in tool_calls if tc.get("id")}
        seen_ids: set[str] = set()
        j = i + 1
        while j < len(messages) and messages[j].get("role") == "tool":
            if (tcid := messages[j].get("tool_call_id")) is not None:
                seen_ids.add(tcid)
            j += 1

        if expected_ids.issubset(seen_ids):
            out.append(msg)
            out.extend(messages[i + 1 : j])
            i = j
        else:
            content = msg.get("content") or ""
            out.append(
                {
                    "role": "assistant",
                    "content": content if content.strip() else "(tool execution interrupted)",
                }
            )
            i = j  # 丢弃 i+1 ~ j-1 的"半截 tool 块"
    return out


def trim_history_window(messages: list[dict], max_messages: int) -> list[dict]:
    if max_messages <= 0 or len(messages) <= max_messages:
        return messages
    trimmed = messages[-max_messages:]
    while trimmed and trimmed[0].get("role") == "tool":
        trimmed = trimmed[1:]
    return repair_dangling_tool_calls(trimmed)
```

## 2. 上下文阈值压缩

### 2.1 问题

长会话历史会撑爆 LLM 上下文 / 烧 token。

### 2.2 DataClaw 做法

`SessionStore.compactIfNeeded({ messages, thresholdTokens, openai, model })`：

- 估算消息总 token；
- 超阈值时调用 LLM 做 summarize；
- 用一条 system 角色摘要 + 最近若干消息替换原历史；
- 写回会话存储（带 `compacted_at` 元信息）。

### 2.3 在 agent-platform 落地

```python
# src/agent_platform/application/orchestration/context_compactor.py
from __future__ import annotations
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

SUMMARY_PROMPT = (
    "You are a conversation summarizer. Compress the following dialog turns into a concise "
    "Markdown summary that preserves: (1) the user goal, (2) key facts/decisions, (3) any "
    "open questions and pending tool results. Do NOT invent details."
)


@dataclass
class CompactionPolicy:
    threshold_tokens: int = 24_000
    keep_recent_messages: int = 6


class ContextCompactor:
    def __init__(self, llm_client, model: str, policy: CompactionPolicy) -> None:
        self._llm = llm_client
        self._model = model
        self._policy = policy

    async def compact_if_needed(
        self, messages: list[dict], estimate_tokens
    ) -> list[dict]:
        total = estimate_tokens(messages)
        if total < self._policy.threshold_tokens:
            return messages

        keep = self._policy.keep_recent_messages
        head = messages[: max(0, len(messages) - keep)]
        tail = messages[len(messages) - keep :] if keep > 0 else []

        try:
            summary = await self._summarize(head)
        except Exception:
            log.warning("[compactor] summarize failed; skipping", exc_info=True)
            return messages

        compacted_head = [{"role": "system", "content": f"## Conversation summary\n{summary}"}]
        return compacted_head + tail

    async def _summarize(self, head: list[dict]) -> str:
        resp = await self._llm.chat_completion(
            model=self._model,
            temperature=0,
            max_completion_tokens=2048,
            messages=[
                {"role": "system", "content": SUMMARY_PROMPT},
                {
                    "role": "user",
                    "content": "\n\n".join(
                        f"[{m.get('role')}] {m.get('content','')}" for m in head if m.get("content")
                    ),
                },
            ],
        )
        return (resp.choices[0].message.content or "").strip()
```

## 3. 启发式重试（避免"早停"）

DataClaw 在 agent loop 末尾根据"模型输出 + tool 历史"判断是否要再追问一句重试指令：

| 触发条件 | 注入的 user message |
|---|---|
| 已用 tool 但 text 为空且无 stdout/fallback | "Runtime instruction: you already have tool observations. Produce the final response now..." |
| 文本看起来像"我无法/请你提供..."但还有可用工具 | "Runtime instruction: do not stop early. Use available tools proactively..." |
| 用户问可视化但没生成图 | "Runtime instruction: this is a visualization task. Use execute_python directly..." |

每个触发只发**一次**（用 `forced*Retry` 标记防循环）。

### 3.1 在 agent-platform 抽象成 `RetryHeuristic`

```python
# src/agent_platform/application/orchestration/retry_heuristics.py
from __future__ import annotations
import re
from dataclasses import dataclass, field

PREMATURE_STOP_RE = re.compile(
    r"请(?:先)?提供|请上传|请补充|需要你|你先|请手动|请自行|无法(?:继续|确定|判断|完成|获取|读取|查看)|"
    r"please provide|please upload|cannot access|insufficient information|need more information|"
    r"unable to continue",
    re.IGNORECASE,
)


@dataclass
class RetryHeuristic:
    name: str
    instruction: str
    fired: bool = False

    def maybe_fire(self, *, response_text: str, used_tools: list[str], tools_available: int,
                   last_tool_stdout: str, last_tool_fallback: str) -> str | None:
        raise NotImplementedError


class ProactiveTryHeuristic(RetryHeuristic):
    def maybe_fire(self, **ctx) -> str | None:
        if self.fired:
            return None
        if ctx["used_tools"]:
            return None
        if ctx["tools_available"] == 0:
            return None
        if not PREMATURE_STOP_RE.search(ctx["response_text"]):
            return None
        self.fired = True
        return self.instruction


class SynthesizeFromObservationsHeuristic(RetryHeuristic):
    def maybe_fire(self, **ctx) -> str | None:
        if self.fired:
            return None
        if not ctx["used_tools"]:
            return None
        if ctx["response_text"]:
            return None
        if ctx["last_tool_stdout"] or ctx["last_tool_fallback"]:
            return None
        self.fired = True
        return self.instruction
```

agent loop 在判断"准备返回 final text"前，按顺序问每个 heuristic 是否要追注入一条 user 指令再跑一轮。

## 4. SOUL 注入分段

DataClaw 每轮把 system prompt 分成 5 段拼接，便于排查：

```
${baseSoul}
${scopeSection}        # user_id / agent_id / agent_name / memory_context
${dailySection}        # 当日 + 昨日的 daily notes
${longTermSection}     # 长期用户记忆（仅 main session）
${autonomySection}     # "尽量端到端完成任务" 这类策略提示
```

### 4.1 在 agent-platform 落地

`application/orchestration/system_prompt_builder.py` 显式拆 5 段，每段独立函数，命中条件清晰可测。Trace 元数据要带每段的 hash 与长度。

## 5. Tool 事件透出（流式进度反馈）

DataClaw 在 IM 入口需要"3 秒内有反馈，否则用户感受不到"。`agentLoop` 通过 `onToolEvent({ stage, name, summary })` 把 tool 调用事件透出到 wecomGateway，由 wecomGateway 转换成进度条与 SQL 状态摘要。

### 5.1 在 agent-platform 抽象

```python
# src/agent_platform/application/orchestration/tool_event_bus.py
from typing import Awaitable, Callable, Literal, TypedDict

class ToolEvent(TypedDict, total=False):
    stage: Literal["start", "progress", "done"]
    name: str
    summary: str

ToolEventCallback = Callable[[ToolEvent], Awaitable[None] | None]
```

任何入口（API / IM / CLI）都可以传一个 `on_tool_event` 回调到 `application/agent.py`，agent loop 在每次工具调用前后调用它。

## 6. 数值与魔数

DataClaw 的关键阈值（搬到 agent-platform 时建议保留作为 `Settings` 字段）：

| 字段 | 默认 | 说明 |
|---|---|---|
| `max_turns` | 10 | tool loop 最大轮数 |
| `compact_threshold_tokens` | 24000 | 压缩触发阈值 |
| `default_max_tokens` | 4096 | LLM `max_completion_tokens` |
| `max_history_messages` | 10 | 历史窗口（compact 之后） |
| `tool_event_summary_max_chars` | 180 | tool event summary 截断长度 |

## 7. 迁移步骤

1. **PR-1**：`history_repair.py` + 单测（覆盖：完整、丢失、tool 起头、空 assistant）。
2. **PR-2**：`context_compactor.py` + 集成单测（mock LLM 返回固定 summary）。
3. **PR-3**：`retry_heuristics.py` + 至少 2 个内置 heuristic + 单测（每个只触发一次）。
4. **PR-4**：`system_prompt_builder.py` 拆 5 段 + trace 元数据。
5. **PR-5**：`ToolEvent` 事件总线 + 在 `application/agent.py` 注入；FastAPI 入口先支持回调日志，后续接 SSE/WS。

## 8. 验收标准

- [ ] 历史里人为留一个 dangling tool call → 修复后 OpenAI API 不报错；
- [ ] 历史 token 超阈值 → 自动 summarize，下一轮 LLM 输入消息数 = 1(summary) + keep_recent；
- [ ] LLM 输出"请你先提供数据" + 还有未用工具 → 自动注入 proactive instruction 并再跑一轮；同条件第二次不再触发；
- [ ] tool event 回调被 agent loop 严格按 `start → done` 顺序调用；
- [ ] 配置中 `max_turns=10` 时绝对不会跑第 11 轮。

## 9. 对照源码

| dataclaw 位置 | agent-platform 目标 |
|---|---|
| `src/services/agentLoop.ts::repairDanglingToolCalls / trimHistoryWindow` | `application/orchestration/history_repair.py` |
| `src/stores/sessionStore.ts::compactIfNeeded` | `application/orchestration/context_compactor.py` |
| `src/services/agentLoop.ts::looksLikePrematureStopResponse / forcedProactiveRetry / forcedObservationSynthesisRetry` | `application/orchestration/retry_heuristics.py` |
| `src/services/agentLoop.ts::buildInjectedSoul` | `application/orchestration/system_prompt_builder.py` |
| `src/services/agentLoop.ts::emitToolEvent` | `application/orchestration/tool_event_bus.py` |
