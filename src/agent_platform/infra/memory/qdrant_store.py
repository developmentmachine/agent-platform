"""Qdrant 向量存储：本地 / 远程同一套客户端配置。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from agent_platform.config.settings import Settings
from agent_platform.infra.memory.protocols import VectorStore

logger = logging.getLogger("agent_platform.memory.qdrant")


class QdrantVectorStore(VectorStore):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._collection = (settings.qdrant_collection or "agent_platform_memory").strip()
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from qdrant_client import QdrantClient
        except Exception as e:
            raise RuntimeError(
                "qdrant-client 未安装。请执行 uv sync / pip install qdrant-client"
            ) from e

        url = (self._settings.qdrant_url or "").strip()
        if not url:
            raise RuntimeError("RECAP_QDRANT_URL 未配置")
        api_key = (self._settings.qdrant_api_key or "").strip() or None
        self._client = QdrantClient(url=url, api_key=api_key)
        return self._client

    def ensure_collection(self, *, vector_size: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        client = self._get_client()
        if client.collection_exists(self._collection):
            return
        client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        logger.info(
            "created qdrant collection=%s vector_size=%s", self._collection, vector_size
        )

    def upsert(
        self,
        items: Sequence[Dict[str, Any]],
        *,
        collection: Optional[str] = None,
    ) -> None:
        if not items:
            return
        from qdrant_client.models import PointStruct

        client = self._get_client()
        coll = collection or self._collection
        size = len(items[0]["vector"])
        self.ensure_collection(vector_size=size)
        qpoints = []
        for p in items:
            pid = p["id"]
            qpoints.append(
                PointStruct(
                    id=str(pid),
                    vector=list(p["vector"]),
                    payload=dict(p.get("payload") or {}),
                )
            )
        client.upsert(collection_name=coll, points=qpoints, wait=True)

    def query(
        self,
        vector: Sequence[float],
        *,
        top_k: int = 5,
        collection: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = self._get_client()
        coll = collection or self._collection
        flt: Optional[Filter] = None
        if filter:
            must = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filter.items()]
            flt = Filter(must=must)
        hits = client.search(
            collection_name=coll,
            query_vector=list(vector),
            limit=top_k,
            query_filter=flt,
            with_payload=True,
        )
        out: List[Dict[str, Any]] = []
        for h in hits or []:
            out.append(
                {
                    "id": str(h.id),
                    "score": float(h.score) if h.score is not None else 0.0,
                    "payload": dict(h.payload or {}),
                }
            )
        return out
