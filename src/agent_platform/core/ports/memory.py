"""记忆 Port：嵌入器 + 向量存储；兼容现有 ``infrastructure.memory.protocols``。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable


@runtime_checkable
class EmbeddingsPort(Protocol):
    """文本 → 向量。"""

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        ...


@runtime_checkable
class VectorStorePort(Protocol):
    """向量库的最小读写抽象。"""

    def upsert(
        self,
        items: Sequence[Dict[str, Any]],
        *,
        collection: Optional[str] = None,
    ) -> None:
        ...

    def query(
        self,
        vector: Sequence[float],
        *,
        top_k: int = 5,
        collection: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """返回 ``[{id, score, payload}, ...]``。"""
        ...
