# 04 · 会话级互斥队列

> **状态**：agent-platform 当前没有"按会话串行化"的机制。在 IM 重发、HTTP 重试、调度任务与用户请求撞车时，同一 session 会并发跑 agent loop，导致**消息顺序错乱**和**会话存储覆盖**。

## 1. 背景

agent 系统典型的并发踩踏场景：

- 用户在 IM 里连发 3 条消息（毫秒级间隔）；
- HTTP 客户端开了重试；
- 后台心跳任务和实时请求撞车；
- 同一会话被两个入口（HTTP + IM）同时打到。

如果不在"会话粒度"做串行，session_messages、tool_calls、memory store 都会出现竞态：

- 历史消息被错序写入；
- `assistant.tool_calls` 还没 append 完，下一个请求已经开始装 system prompt（dataclaw 在 agentLoop 里专门写了 `repairDanglingToolCalls` 兜底，但治本应该是入口侧串行）；
- 长期记忆被同时改写，最后写入者赢。

## 2. DataClaw 实现（30 行）

源码：`/Users/zhaichuancheng/DevelopSpace/dataclaw/src/services/sessionQueue.ts`

```ts
export class SessionQueue {
  private readonly tails = new Map<string, Promise<void>>();

  async runExclusive<T>(key: string, task: () => Promise<T>): Promise<T> {
    const previous = this.tails.get(key) ?? Promise.resolve();
    let releaseCurrent: () => void;
    const current = new Promise<void>((resolve) => { releaseCurrent = resolve; });
    this.tails.set(key, previous.then(() => current));

    await previous;
    try {
      return await task();
    } finally {
      releaseCurrent!();
      if (this.tails.get(key) === current) {
        this.tails.delete(key);
      }
    }
  }
}
```

`MessageProcessor.process` 里包了一层：

```ts
return this.queue.runExclusive(scopeKey, async () => { ... });
```

`scopeKey` 由 `${channelId}:${tenantId}:${peerId}` 拼成，保证"同一渠道/租户/对端"的请求严格串行。

## 3. 在 agent-platform 的目标位置

```
src/agent_platform/
  application/
    concurrency/
      __init__.py
      session_lock.py       # SessionLockRegistry
  interfaces/api/v1/
    feedback.py / jobs.py / recap.py    # 在入口处用
```

## 4. Python 实现骨架

### 4.1 单进程版（`asyncio.Lock` per key）

```python
# src/agent_platform/application/concurrency/session_lock.py
from __future__ import annotations
import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

@dataclass
class _LockEntry:
    lock: asyncio.Lock
    waiters: int = 0
    last_used_at: float = 0.0


class SessionLockRegistry:
    """Per-key 串行执行队列。

    用法：
        async with registry.acquire(scope_key):
            await do_work()

    特点：
    - 同一 key 的并发请求严格串行（FIFO）；
    - 不同 key 完全并发；
    - 自动清理空闲 lock，避免内存泄漏；
    - 支持可选超时，避免长任务卡死后续请求。
    """

    def __init__(self, idle_ttl_s: float = 300.0) -> None:
        self._entries: dict[str, _LockEntry] = {}
        self._registry_lock = asyncio.Lock()
        self._idle_ttl_s = idle_ttl_s

    async def _get_or_create(self, key: str) -> _LockEntry:
        async with self._registry_lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = _LockEntry(lock=asyncio.Lock(), last_used_at=time.monotonic())
                self._entries[key] = entry
            entry.waiters += 1
            return entry

    async def _release(self, key: str, entry: _LockEntry) -> None:
        async with self._registry_lock:
            entry.waiters -= 1
            entry.last_used_at = time.monotonic()
            if entry.waiters <= 0 and not entry.lock.locked():
                # 真的没人用了 -> GC
                self._entries.pop(key, None)

    @asynccontextmanager
    async def acquire(self, key: str, timeout_s: float | None = None):
        entry = await self._get_or_create(key)
        try:
            if timeout_s is None:
                await entry.lock.acquire()
            else:
                await asyncio.wait_for(entry.lock.acquire(), timeout=timeout_s)
            try:
                yield
            finally:
                entry.lock.release()
        finally:
            await self._release(key, entry)

    def stats(self) -> dict:
        return {
            "active_keys": len(self._entries),
            "locked_keys": sum(1 for e in self._entries.values() if e.lock.locked()),
            "total_waiters": sum(e.waiters for e in self._entries.values()),
        }
```

### 4.2 分布式版（Redis 锁）

如果 agent-platform 部署多实例（K8s 多 pod），上面的进程内锁不够用，需要分布式锁。

```python
# src/agent_platform/application/concurrency/session_lock_redis.py
from __future__ import annotations
import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from redis.asyncio import Redis

log = logging.getLogger(__name__)
RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class RedisSessionLock:
    def __init__(
        self,
        redis: Redis,
        prefix: str = "agent:lock:",
        ttl_s: int = 120,
        retry_interval_s: float = 0.05,
        max_wait_s: float = 30.0,
    ) -> None:
        self._redis = redis
        self._prefix = prefix
        self._ttl_s = ttl_s
        self._retry = retry_interval_s
        self._max_wait = max_wait_s

    @asynccontextmanager
    async def acquire(self, key: str):
        token = secrets.token_hex(16)
        full_key = self._prefix + key
        deadline = asyncio.get_event_loop().time() + self._max_wait
        # spin
        while True:
            ok = await self._redis.set(full_key, token, nx=True, ex=self._ttl_s)
            if ok:
                break
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(f"acquire session lock timeout: {key}")
            await asyncio.sleep(self._retry)
        try:
            # 后台续约（避免长任务超过 ttl）
            renew_task = asyncio.create_task(self._renew(full_key, token))
            try:
                yield
            finally:
                renew_task.cancel()
                try:
                    await renew_task
                except asyncio.CancelledError:
                    pass
        finally:
            try:
                await self._redis.eval(RELEASE_LUA, 1, full_key, token)
            except Exception:
                log.warning("[redis-lock] release failed key=%s", key, exc_info=True)

    async def _renew(self, full_key: str, token: str) -> None:
        try:
            while True:
                await asyncio.sleep(self._ttl_s / 3)
                renew_ok = await self._redis.eval(
                    """
                    if redis.call("get", KEYS[1]) == ARGV[1] then
                        return redis.call("expire", KEYS[1], ARGV[2])
                    else
                        return 0
                    end
                    """,
                    1, full_key, token, self._ttl_s,
                )
                if not renew_ok:
                    log.warning("[redis-lock] renew lost key=%s", full_key)
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("[redis-lock] renew failed key=%s", full_key, exc_info=True)
```

### 4.3 接入入口

在 `interfaces/api/v1/recap.py` 等入口的请求处理函数：

```python
# 伪代码
scope_key = f"{channel_id}:{tenant_id}:{peer_id}"
async with session_locks.acquire(scope_key, timeout_s=120):
    return await agent_app.run_turn(req, ctx)
```

CLI / scheduler 入口同样需要包，避免与 HTTP 撞车。

## 5. 配置

`.env.example` 增量：

```bash
SESSION_LOCK_BACKEND=local                  # local | redis
SESSION_LOCK_IDLE_TTL_S=300
SESSION_LOCK_TIMEOUT_S=120
# 仅 redis 后端
SESSION_LOCK_REDIS_URL=redis://localhost:6379/0
SESSION_LOCK_REDIS_TTL_S=120
```

## 6. scope_key 怎么拼

参考 dataclaw `MessageProcessor.buildScopeKey`：

```
${channel}:${tenant}:${normalized_peer_id}
```

- `channel`：`http` / `wecom` / `cli` / `scheduler`；
- `tenant`：多租户标识（默认 `default`）；
- `peer_id`：单聊用 `dm:<user_id>`，群聊用 `group:<chat_id>:<user_id>`（保证"同一群里不同人"也能并发）。

## 7. 迁移步骤

1. **PR-1**：`SessionLockRegistry`（本地版）+ 单测（并发触发 100 个相同 key，检查严格串行）。
2. **PR-2**：在 `interfaces/api/v1/*.py` 入口包一层 `acquire(scope_key)`。
3. **PR-3**：（按需）`RedisSessionLock` + 配置切换。

## 8. 验收标准

- [ ] 100 个相同 key 的并发请求，**完成顺序与提交顺序严格一致**；
- [ ] 不同 key 的请求并发执行（不串行）；
- [ ] 任务异常时锁能被正确释放（不死锁）；
- [ ] `stats()` 显示空闲 key 不会无限增长（GC 生效）；
- [ ] Redis 版：实例 A 持有锁时实例 B 阻塞等待，A 进程崩溃后 B 在 ttl 内能拿到锁。

## 9. 对照源码

| dataclaw 位置 | agent-platform 目标 |
|---|---|
| `src/services/sessionQueue.ts::SessionQueue` | `application/concurrency/session_lock.py::SessionLockRegistry` |
| `src/services/processor.ts::buildScopeKey` | 各入口拼 scope_key 的小工具函数 |
| 隐式（dataclaw 单进程） | `application/concurrency/session_lock_redis.py::RedisSessionLock`（多实例时） |
