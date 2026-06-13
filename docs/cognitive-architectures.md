# 认知架构指南

> Agent Platform 支持多种认知架构，新 Agent 可按需选用。
> 所有架构原语都在 `core/orchestration/`，与具体 Agent 解耦。

---

## 支持的认知架构总览

| 架构 | 原语 | 适用场景 | 复杂度 |
|------|------|----------|--------|
| **Pipeline** | `Pipeline` + `Phase` | 线性多阶段处理 | ⭐ |
| **ReAct** | `ReActLoop` | 需要推理+工具调用的交互任务 | ⭐⭐ |
| **Plan-and-Execute** | `PlanExecutePipeline` | 复杂任务分解+动态调整 | ⭐⭐⭐ |
| **直接函数调用** | 无（纯 Python） | 简单对话、单轮任务 | ⭐ |
| ~~Multi-Agent~~ | — | — | （规划中） |

---

## 1. Pipeline（线性 Phase 执行）

**适用场景**：任务可以分解为固定顺序的阶段，每个阶段做一件明确的事。

**典型用例**：数据采集 → 特征工程 → LLM 生成 → 评测 → 持久化（stock-recap 就是这个模式）

```python
from agent_platform.core.orchestration import Pipeline, Phase, RunState, StreamEvent

class PerceivePhase(Phase):
    name = "perceive"
    def run(self, state): state.data = collect_data(state.request)
    def stream(self, state):
        yield StreamEvent(kind=StreamEventKind.PHASE_START, phase=self.name)
        self.run(state)
        yield StreamEvent(kind=StreamEventKind.PHASE_END, phase=self.name)

class ActPhase(Phase):
    name = "act"
    def run(self, state): state.result = llm_generate(state.data)
    def stream(self, state):
        yield StreamEvent(kind=StreamEventKind.PHASE_START, phase=self.name)
        self.run(state)
        yield StreamEvent(kind=StreamEventKind.PHASE_END, phase=self.name)

# 使用
pipeline = Pipeline([PerceivePhase(), ActPhase()])
pipeline.execute(state)       # 同步
list(pipeline.stream(state))  # 流式 NDJSON
```

**特点**：
- 固定阶段顺序，不支持动态调整
- 内置 budget 检查、OTEL span、SideEffectBus 事件
- 最简单的认知架构，适合数据处理流水线

---

## 2. ReAct（推理 + 行动循环）

**适用场景**：需要 LLM 反复推理、调用工具、观察结果的交互式任务。

**典型用例**：搜索问答、数据分析助手、多步查询

```python
from agent_platform.core.orchestration import ReActLoop, ReActState

# 1. 定义 LLM 调用和工具
def my_llm(messages):
    return call_my_llm(messages)  # 返回文本

def my_tool(name, input_data):
    if name == "search":
        return search_api(input_data["query"])
    if name == "calculate":
        return str(eval(input_data["expression"]))

# 2. 创建状态
state = ReActState(
    run_ctx=RunContext.new(),
    principal=PrincipalContext.anonymous(source="api"),
    task="查询今日A股涨幅前5的板块，并计算平均涨幅",
    system_prompt="你是一个数据分析助手",
    tools={
        "search": my_tool,
        "calculate": my_tool,
    },
    llm_caller=my_llm,
    # tool_parser 使用默认解析器（也可自定义）
)

# 3. 执行
loop = ReActLoop(max_iterations=8)
loop.execute(state)

print(state.final_answer)
for step in state.steps:
    print(f"  Thought: {step.thought}")
    print(f"  Action: {step.action}({step.action_input})")
    print(f"  Observation: {step.observation}")
```

**ReAct 循环流程**：
```
Task → LLM 推理 → [Final Answer?] → 结束
                   ↓ No
              [Action: tool_name]
                   ↓
              执行工具 → Observation
                   ↓
              反馈给 LLM → 继续推理
```

**流式输出**：
```python
for event in loop.stream(state):
    if event.kind == StreamEventKind.REACT_THOUGHT_END:
        print(f"💭 {event.data['thought']}")
    elif event.kind == StreamEventKind.REACT_ACTION:
        print(f"🔧 {event.data['action']}({event.data['input']})")
    elif event.kind == StreamEventKind.REACT_OBSERVATION:
        print(f"👁 {event.data['observation']}")
    elif event.kind == StreamEventKind.REACT_ANSWER:
        print(f"✅ {event.data['answer']}")
```

**LLM 输出格式**（默认解析器期望）：
```
Thought: 我需要查询今日板块数据
Action: search
Action Input: {"query": "今日A股板块涨幅排名"}

Observation: 电力板块+2.1%, 煤炭+1.8%...

Thought: 现在我需要计算平均涨幅
Action: calculate
Action Input: {"expression": "(2.1+1.8+1.5+1.3+1.1)/5"}

Observation: 1.56

Thought: 我已经得到了答案
Final Answer: 今日涨幅前5的板块平均涨幅为1.56%
```

**自定义 tool_parser**：
```python
def my_parser(llm_text):
    """如果 LLM 输出不是标准 ReAct 格式，自定义解析。"""
    # 返回 (thought, action, action_input, is_final, answer)
    ...
    return thought, action, action_input, is_final, answer

state.tool_parser = my_parser
```

---

## 3. Plan-and-Execute（计划 → 执行 → 重规划）

**适用场景**：复杂任务需要先分解为子目标，逐步执行，执行中可能需要调整计划。

**典型用例**：研究报告生成、多步数据分析、项目规划

```python
from agent_platform.core.orchestration import PlanExecutePipeline, PlanExecuteState

# 1. 定义规划函数
def my_planner(task, context):
    """LLM 将任务分解为子目标列表。"""
    prompt = f"将以下任务分解为3-5个子步骤:\n{task}"
    result = call_llm([{"role": "user", "content": prompt}])
    return [line.strip() for line in result.strip().split("\n") if line.strip()]

def my_executor(subgoal, context):
    """执行单个子目标。"""
    prompt = f"请完成以下任务:\n{subgoal}"
    return call_llm([{"role": "user", "content": prompt}])

def my_replanner(task, completed, remaining, context):
    """根据已完成的结果，修订剩余计划。"""
    completed_summary = "\n".join(f"- {g.description}: {g.result}" for g in completed)
    remaining_list = "\n".join(f"- {g.description}" for g in remaining)
    prompt = (
        f"任务: {task}\n\n"
        f"已完成:\n{completed_summary}\n\n"
        f"剩余计划:\n{remaining_list}\n\n"
        f"根据已完成的结果，修订剩余计划。如果不需要修改，原样返回。"
    )
    result = call_llm([{"role": "user", "content": prompt}])
    return [line.strip() for line in result.strip().split("\n") if line.strip()]

# 2. 创建状态
state = PlanExecuteState(
    run_ctx=RunContext.new(),
    principal=PrincipalContext.anonymous(source="api"),
    task="撰写一份2024年A股市场年度回顾报告",
    planner_fn=my_planner,
    executor_fn=my_executor,
    replanner_fn=my_replanner,  # 可选，不提供则不重规划
    context={"style": "专业分析"},
)

# 3. 执行
pipeline = PlanExecutePipeline(max_replans=3)
pipeline.execute(state)

print(state.final_answer)
for g in state.subgoals:
    print(f"  [{g.status.value}] {g.description}")
    if g.result:
        print(f"    → {g.result[:100]}")
```

**Plan-and-Execute 流程**：
```
Task → Planner 生成子目标列表
         ↓
     [Subgoal 1] → 执行 → 结果
         ↓
     [Replanner] → 修订剩余计划？ → [Subgoal 2] → ...
         ↓
     聚合所有结果 → Final Answer
```

**不使用 replanner**（纯线性执行）：
```python
state = PlanExecuteState(
    ...,
    replanner_fn=None,  # 不重规划
)
pipeline = PlanExecutePipeline(max_replans=0)
```

---

## 4. 直接函数调用（最简模式）

**适用场景**：简单的对话、单轮任务，不需要复杂的编排。

**典型用例**：hsk30-tutor（中文陪练）

```python
def chat_turn(request, settings):
    """hsk30-tutor 就是这种模式。"""
    messages = build_messages(request)
    response = call_llm(messages)
    validation = validate_output(response, settings)
    if not validation.ok:
        # 重试
        messages.append({"role": "user", "content": f"请修正: {validation.error}"})
        response = call_llm(messages)
    return response
```

**不需要 Pipeline/Phase，直接用 Python 函数即可。**

---

## 5. 新 Agent 选型指南

### 决策树

```
你的 Agent 需要什么？
│
├─ 简单对话/单轮任务 → 直接函数调用（hsk30-tutor 模式）
│
├─ 固定阶段的数据流水线 → Pipeline + Phase（stock-recap 模式）
│
├─ 需要推理+工具调用的交互任务 → ReActLoop
│   例：搜索问答、数据分析助手
│
├─ 复杂任务需要分解+动态调整 → PlanExecutePipeline
│   例：研究报告、多步项目
│
└─ 多个 Agent 协作 → （规划中，暂不支持）
```

### 选型对比

| 特性 | 直接调用 | Pipeline | ReAct | Plan-Execute |
|------|----------|----------|-------|--------------|
| 固定阶段 | ✅ | ✅ | ❌ | ❌ |
| 动态决策 | ❌ | ❌ | ✅ | ✅ |
| 工具调用 | 手动 | Phase 内 | 内置循环 | Executor 内 |
| 流式输出 | 手动 | ✅ | ✅ | ✅ |
| Budget 检查 | 手动 | 自动 | 自动 | 自动 |
| 复杂度 | 低 | 低 | 中 | 高 |

### 接入方式

#### 步骤 1：选择架构

根据上面的决策树选择。

#### 步骤 2：实现 Agent 代码

**ReAct 接入示例**：

```python
# agents/my_agent/react_runner.py
from agent_platform.core.orchestration import ReActLoop, ReActState

def run_react_task(task, settings, *, tools, llm_caller):
    state = ReActState(
        run_ctx=current_run_context.get(),
        principal=current_principal.get(),
        task=task,
        tools=tools,
        llm_caller=llm_caller,
        system_prompt="你是一个...",
        max_iterations=8,
    )
    loop = ReActLoop(max_iterations=8)
    loop.execute(state)
    return state.final_answer
```

**Plan-Execute 接入示例**：

```python
# agents/my_agent/plan_runner.py
from agent_platform.core.orchestration import PlanExecutePipeline, PlanExecuteState

def run_plan_task(task, settings, *, planner, executor, replanner=None):
    state = PlanExecuteState(
        run_ctx=current_run_context.get(),
        principal=current_principal.get(),
        task=task,
        planner_fn=planner,
        executor_fn=executor,
        replanner_fn=replanner,
    )
    pipeline = PlanExecutePipeline(max_replans=3)
    pipeline.execute(state)
    return state.final_answer
```

#### 步骤 3：在 manifest.py 中注册

```python
def _runner(*, envelope, principal, session, run_ctx, settings, runtime):
    req = MyRequest.model_validate(envelope.payload)

    # 根据请求参数选择架构
    if req.architecture == "react":
        result = run_react_task(req.task, settings, tools=my_tools, llm_caller=my_llm)
    elif req.architecture == "plan_execute":
        result = run_plan_task(req.task, settings, planner=my_planner, executor=my_executor)
    else:
        result = run_simple(req, settings)

    return AgentResponseEnvelope(agent_id=AGENT_ID, request_id=run_ctx.request_id, payload={"answer": result})
```

#### 步骤 4：测试

```python
def test_my_agent_react():
    state = ReActState(
        run_ctx=RunContext.new(),
        principal=PrincipalContext.anonymous(source="test"),
        task="test task",
        tools={"mock_tool": lambda n, i: "mock result"},
        llm_caller=lambda msgs: "Thought: done\nFinal Answer: 42",
    )
    ReActLoop(max_iterations=3).execute(state)
    assert state.final_answer == "42"
```

---

## 6. 组合架构

不同架构可以在同一个 Agent 内组合使用：

```python
class DataPhase(Phase):
    """Pipeline 中的某个 Phase 内部使用 ReAct。"""
    name = "data_analysis"

    def run(self, state):
        react_state = ReActState(
            task="分析数据趋势",
            tools=state.tools,
            llm_caller=state.llm_caller,
        )
        ReActLoop(max_iterations=5).execute(react_state)
        state.analysis = react_state.final_answer
```

---

## 7. 自定义认知架构

如需实现平台未提供的架构（如 Tree of Thoughts、辩论模式等）：

1. 在 `core/orchestration/` 新建模块
2. 继承或组合 `RunState`、`StreamEventKind`、`SideEffectBus`
3. 提供 `execute(state)` 和 `stream(state)` 方法
4. 添加测试

```python
# core/orchestration/my_architecture.py
from agent_platform.core.orchestration.run_state import RunState
from agent_platform.core.orchestration.stream_events import StreamEvent, StreamEventKind

class MyArchitectureState(RunState):
    task: str = ""
    # ... 自定义字段

class MyArchitecture:
    def execute(self, state: MyArchitectureState) -> None: ...
    def stream(self, state: MyArchitectureState) -> Iterator[StreamEvent]: ...
```

**约束**：core/orchestration/ 不得 import agents/ 或 infra/（import-linter 强制）。
