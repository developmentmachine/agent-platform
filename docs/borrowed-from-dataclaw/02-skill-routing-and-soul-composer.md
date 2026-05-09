# 02 · Skill 路由 + SOUL 装配

> **状态**：agent-platform 现有 `skills/<name>/SKILL.md + manifest.json` 是**静态的**，缺少"按用户输入动态选择"的能力，也没有显式的"system prompt 装配"对象。本专题把这两件事补齐。

## 1. 背景与价值

**Skill 路由**回答的是"这次请求该激活哪些 skill"。Skill 数量过百时不可能全塞 system prompt。

**SOUL 装配**回答的是"最终发给 LLM 的 system prompt 长什么样、由谁拼接、留下什么 trace"——这是 agent 系统**最大的黑盒**，必须建模成一等公民对象，否则线上排障极其痛苦。

DataClaw 的做法是：

1. **关键词打分**（含中文 2-gram/3-gram 兜底）
2. **+ LLM intent 路由**（小模型 + JSON 输出 + allowlist 校验，加 500 分 boost）
3. **+ Top-K 上限**（`maxActiveSkills`）
4. **+ 静默回退**（LLM 调用任何失败回到关键词模式）
5. **SOUL = baseSoul + 激活 skills 列表 + resources 清单**，并返回完整的 `routing` 元信息（mode/llmEnabled/llmSelectedSkills/fallbackToKeyword/activatedSkillNames）

## 2. DataClaw 实现拆解

源码：`/Users/zhaichuancheng/DevelopSpace/dataclaw/src/services/skills.ts`

### 2.1 关键词打分 `scoreSkill()`

- skill 名称命中文本：+100；
- 关键词集合（来自 `name + description`）每命中一个：+1；
- 中文长 token（>4）拆 2-gram + 3-gram 提升中文召回。

```ts
// 摘录 src/services/skills.ts
const isChinese = /^[\u4e00-\u9fa5]+$/.test(token);
if (isChinese && token.length > 4) {
  result.push(token);
  for (let i = 0; i <= token.length - 2; i++) result.push(token.slice(i, i + 2));
  for (let i = 0; i <= token.length - 3; i++) result.push(token.slice(i, i + 3));
}
```

### 2.2 LLM intent 路由 `inferSkillsByLlmIntent()`

- 用小模型（同 `openaiModel`）+ `response_format: json_object`；
- system prompt：`"You are a skill router. Select only the skills that are genuinely needed... Return strict JSON: {\"skills\":[\"skill-name\"]}"`；
- user content：`{"request": userText, "skills": [{name, description}, ...]}`；
- 解析后用 allowlist 过滤掉幻觉名字；
- 任何异常（网络/JSON parse/格式错）→ 返回空 set（静默回退到关键词模式）；
- 命中的 skill 在打分阶段获得 `+500` boost，与关键词分数融合排序后取 Top-K。

### 2.3 SOUL 装配 `composeSoulWithIntent()`

```
${baseSoul}

# Activated Skills
Follow the skill instructions below when they are relevant to the current user request.

## Skill: <name>
Description: <description>
Source: <project|workspace|oceanbase|bos>
Instructions:
<body>

Available resources (use list_skill_files / load_skill_resource to load):
- references/foo — <desc>
- scripts/bar — <desc>
```

返回结构：

```ts
interface SkillActivationResult {
  soul: string;                    // 拼好的最终 system prompt
  activatedSkills: SkillDefinition[];
  routing: {
    mode: 'llm+keyword' | 'keyword-only';
    llmEnabled: boolean;
    llmSelectedSkills: string[];
    fallbackToKeyword: boolean;
    activatedSkillNames: string[];
  };
}
```

## 3. 在 agent-platform 的目标位置

```
src/agent_platform/
  domain/
    skills.py                   # SkillDefinition / SkillResource / 协议
  application/
    skills/
      __init__.py
      router.py                 # SkillRouter（关键词 + LLM intent + Top-K）
      soul_composer.py          # SoulComposer（装配 system prompt + routing 元信息）
  infrastructure/
    skills/
      __init__.py
      keyword_index.py          # 中文 2/3-gram 关键词抽取
      llm_intent.py             # LLM 调用封装
```

## 4. Python 实现骨架

### 4.1 领域模型

```python
# src/agent_platform/domain/skills.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

SkillSource = Literal["project", "workspace", "user", "remote"]
SkillResourceCategory = Literal["references", "scripts", "assets", "templates"]


@dataclass(frozen=True)
class SkillResource:
    path: str                                 # e.g. "references/foo"
    category: SkillResourceCategory
    file_name: str
    description: str
    sort_order: int
    file_path: str                            # 真实路径（FS / object key）


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    instructions: str                          # SKILL.md body
    source: SkillSource
    resources: tuple[SkillResource, ...] = ()


@runtime_checkable
class SkillRepository(Protocol):
    async def discover(self) -> list[SkillDefinition]: ...
    async def discover_user_skills(self, user_id: str) -> list[SkillDefinition]: ...
```

### 4.2 关键词索引

```python
# src/agent_platform/infrastructure/skills/keyword_index.py
import re

_TOKEN_PATTERN = re.compile(r"[^\w\u4e00-\u9fa5_-]+", re.UNICODE)
_CN_PATTERN = re.compile(r"^[\u4e00-\u9fa5]+$")


def extract_keywords(text: str) -> list[str]:
    out: list[str] = []
    for raw in _TOKEN_PATTERN.split(text.lower()):
        token = raw.strip()
        if len(token) < 2:
            continue
        if _CN_PATTERN.match(token) and len(token) > 4:
            out.append(token)
            out.extend(token[i : i + 2] for i in range(len(token) - 1))
            out.extend(token[i : i + 3] for i in range(len(token) - 2))
        else:
            out.append(token)
    return out


def unique_keywords(text: str) -> list[str]:
    return list(dict.fromkeys(extract_keywords(text)))


def score_skill(name: str, description: str, user_text: str) -> int:
    lower = user_text.lower()
    score = 0
    if name.lower() in lower:
        score += 100
    for kw in unique_keywords(f"{name} {description}"):
        if kw in lower:
            score += 1
    return score
```

### 4.3 LLM intent 路由

```python
# src/agent_platform/infrastructure/skills/llm_intent.py
from __future__ import annotations
import json
import logging
from typing import Iterable

from agent_platform.domain.skills import SkillDefinition

log = logging.getLogger(__name__)

_SYSTEM = (
    "You are a skill router. Select only the skills that are genuinely needed "
    'to solve the user request. Return strict JSON: {"skills":["skill-name"]}.'
)


class LlmSkillIntentResolver:
    def __init__(self, llm_client, model: str, temperature: float = 0.0) -> None:
        self._llm = llm_client
        self._model = model
        self._temperature = max(0.0, temperature)

    async def resolve(
        self, user_text: str, candidates: Iterable[SkillDefinition]
    ) -> set[str]:
        candidates = list(candidates)
        if not user_text.strip() or not candidates:
            return set()

        catalog = [{"name": s.name, "description": s.description} for s in candidates]
        try:
            resp = await self._llm.chat_completion(
                model=self._model,
                temperature=self._temperature,
                max_completion_tokens=256,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": json.dumps(
                        {"request": user_text, "skills": catalog}, ensure_ascii=False
                    )},
                ],
            )
            content = (resp.choices[0].message.content or "").strip()
            if not content:
                return set()
            parsed = json.loads(content)
            allowed = {s.name for s in candidates}
            picked: set[str] = set()
            for raw in parsed.get("skills", []) or []:
                if not isinstance(raw, str):
                    continue
                normalized = raw.strip().lower()
                if normalized and normalized in allowed:
                    picked.add(normalized)
            return picked
        except Exception:
            # 静默回退到关键词模式，但必须 warn + 计数
            log.warning("[skill-router] LLM intent failed, fallback to keyword", exc_info=True)
            return set()
```

### 4.4 路由器

```python
# src/agent_platform/application/skills/router.py
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Literal

from agent_platform.domain.skills import SkillDefinition, SkillRepository
from agent_platform.infrastructure.skills.keyword_index import score_skill
from agent_platform.infrastructure.skills.llm_intent import LlmSkillIntentResolver

log = logging.getLogger(__name__)
RoutingMode = Literal["llm+keyword", "keyword-only", "unknown"]


@dataclass(frozen=True)
class SkillRoutingDecision:
    mode: RoutingMode
    llm_enabled: bool
    llm_selected: tuple[str, ...]
    fallback_to_keyword: bool
    activated: tuple[SkillDefinition, ...]


class SkillRouter:
    def __init__(
        self,
        repo: SkillRepository,
        intent_resolver: LlmSkillIntentResolver | None,
        max_active: int = 3,
    ) -> None:
        self._repo = repo
        self._resolver = intent_resolver
        self._max_active = max(1, max_active)

    async def route(
        self, user_text: str, user_id: str | None = None
    ) -> SkillRoutingDecision:
        if not user_text.strip():
            return SkillRoutingDecision("unknown", bool(self._resolver), (), False, ())

        system_skills = await self._repo.discover()
        user_skills = (
            await self._repo.discover_user_skills(user_id) if user_id else []
        )
        public_names = {s.name for s in system_skills}
        merged = list(system_skills) + [s for s in user_skills if s.name not in public_names]

        llm_selected: set[str] = set()
        if self._resolver is not None:
            llm_selected = await self._resolver.resolve(user_text, merged)

        scored: list[tuple[SkillDefinition, int]] = []
        for s in merged:
            base = score_skill(s.name, s.description, user_text)
            boost = 500 if s.name in llm_selected else 0
            total = base + boost
            if total > 0:
                scored.append((s, total))

        scored.sort(key=lambda x: (-x[1], x[0].name))
        activated = tuple(s for s, _ in scored[: self._max_active])

        mode: RoutingMode = "llm+keyword" if self._resolver is not None else "keyword-only"
        fallback = self._resolver is not None and not llm_selected

        decision = SkillRoutingDecision(
            mode=mode,
            llm_enabled=self._resolver is not None,
            llm_selected=tuple(sorted(llm_selected)),
            fallback_to_keyword=fallback,
            activated=activated,
        )
        log.info(
            "[skill-router] mode=%s llm=%s selected=%s fallback=%s activated=%s",
            mode, decision.llm_enabled, decision.llm_selected,
            fallback, [s.name for s in activated],
        )
        return decision
```

### 4.5 SOUL 装配器

```python
# src/agent_platform/application/skills/soul_composer.py
from __future__ import annotations
from dataclasses import dataclass

from agent_platform.domain.skills import SkillDefinition
from .router import SkillRoutingDecision


@dataclass(frozen=True)
class ComposedSoul:
    text: str                                  # 最终 system prompt
    routing: SkillRoutingDecision


class SoulComposer:
    """把 baseSoul + 激活 skills + resources 清单组装成最终 system prompt。"""

    def compose(self, base_soul: str, decision: SkillRoutingDecision) -> ComposedSoul:
        if not decision.activated:
            return ComposedSoul(text=base_soul, routing=decision)

        parts: list[str] = [
            base_soul,
            "",
            "# Activated Skills",
            "Follow the skill instructions below when they are relevant to the current user request.",
            "",
        ]
        for s in decision.activated:
            parts.append(self._render_skill(s))
        return ComposedSoul(text="\n".join(parts), routing=decision)

    @staticmethod
    def _render_skill(s: SkillDefinition) -> str:
        section = [
            f"## Skill: {s.name}",
            f"Description: {s.description}",
            f"Source: {s.source}",
            "Instructions:",
            s.instructions,
        ]
        if s.resources:
            section.append("")
            section.append(
                "Available resources "
                "(use `list_skill_files` to enumerate, `load_skill_resource` to load by path):"
            )
            for r in s.resources:
                section.append(f"- {r.path} — {r.description}")
        section.append("")
        return "\n".join(section)
```

### 4.6 注入 application/agent.py

```python
# 伪代码
decision = await skill_router.route(user_text=req.text, user_id=ctx.principal.id)
composed = soul_composer.compose(base_soul=ctx.base_soul, decision=decision)

# 把 composed.text 当 system prompt 给 LLM
# 把 decision 写到 observability/runtime_context 里供 trace
runtime_context.set_skill_routing(decision)
```

## 5. 配置与可观测

`.env.example` 增量：

```bash
SKILL_MAX_ACTIVE=3
SKILL_INTENT_MODEL=gpt-4o-mini             # 留空则禁用 LLM intent，纯关键词
SKILL_INTENT_TEMPERATURE=0
```

`observability/metrics.py` 增量：

```python
skill_router_decisions = Counter("skill_router_decisions_total", ["mode", "fallback"])
skill_router_activated = Counter("skill_router_activated_total", ["skill_name"])
skill_router_llm_failed = Counter("skill_router_llm_failed_total", [])
```

## 6. 迁移步骤

1. **PR-1（domain）**：`domain/skills.py` 协议；让现有 `skills/loader.py` 实现 `SkillRepository` 协议（不破坏现有 manifest 格式）。
2. **PR-2（router + composer）**：`application/skills/{router,soul_composer}.py` + `infrastructure/skills/{keyword_index,llm_intent}.py`，单测覆盖：
   - 中文 2/3-gram 命中
   - LLM 选中的 skill boost 排序
   - LLM 失败 fallback
   - Top-K 截断
3. **PR-3（接入 agent.py）**：把 `application/agent.py` 的"装 system prompt"步骤换成 `SkillRouter + SoulComposer` 调用，产出 `ComposedSoul.routing` 写入 trace。
4. **PR-4（指标）**：观测大盘，验证 7 天 LLM intent 准确率与 fallback 比例。

## 7. 验收标准

- [ ] 中文 query "请帮我做 A 股次日策略" 命中 `a_share_strategy_nextday`；
- [ ] LLM 异常时 metric `skill_router_llm_failed_total` +1，且仍有 keyword 路径返回的激活 skills；
- [ ] `Top-K = 3` 时即使 5 个 skill 都打分 >0，最终 `decision.activated` 只 3 个；
- [ ] `decision.routing` 完整出现在 trace span 元数据里（agent loop 排障可看到）；
- [ ] System prompt 在没有激活 skill 时与原 baseSoul 完全一致（不应留 "# Activated Skills" 空段）。

## 8. 对照源码

| dataclaw 位置 | agent-platform 目标 |
|---|---|
| `src/services/skills.ts::extractKeywords / scoreSkill` | `infrastructure/skills/keyword_index.py` |
| `src/services/skills.ts::inferSkillsByLlmIntent` | `infrastructure/skills/llm_intent.py` |
| `src/services/skills.ts::selectSkillsWithIntent` | `application/skills/router.py` |
| `src/services/skills.ts::composeSoulWithIntent / composeSoulFromActivatedSkills` | `application/skills/soul_composer.py` |
| `src/services/skills.ts::SkillActivationResult.routing` | `domain/skills.py::SkillRoutingDecision`（注：放在 application 也可，看你倾向） |
