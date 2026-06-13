"""HSK 3.0 RAG 引擎 — 基于 TF-IDF 的考纲内容检索。

对任务大纲、语法大纲、话题大纲进行分块，根据用户消息检索最相关的
考纲内容注入 system prompt，替代全量注入以节省 token。

设计决策：
- 使用 jieba 分词 + TF-IDF 余弦相似度（纯 Python，无外部依赖）
- 词汇表和认读字表保持全量注入（验证需要，不可检索）
- 任务/语法/话题大纲按语义段落分块，每块 ~200-500 字
- 语法例句按语法点分块
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Sequence, Tuple

import jieba

from agent_platform.agents.hsk30_tutor.syllabus import get_syllabus
from agent_platform.agents.hsk30_tutor.grammar_examples import get_grammar_examples


# ── 数据模型 ──────────────────────────────────────────────────

@dataclass(frozen=True)
class Chunk:
    """一个检索块。"""
    category: str       # "tasks" | "grammar" | "topics" | "grammar_examples"
    level: int          # 1-9
    title: str          # 块标题（用于 prompt 展示）
    content: str        # 块内容
    tokens: List[str] = field(default_factory=list, repr=False)  # jieba 分词结果


# ── 分块策略 ──────────────────────────────────────────────────

def _split_sections(text: str, min_len: int = 100) -> List[Tuple[str, str]]:
    """将大纲文本按「一、二、三…」或「（一）（二）…」分段。

    返回 [(title, content), ...]
    """
    # 匹配「一、」「二、」… 或「（一）」「（二）」…
    pattern = r'(?=\n?[一二三四五六七八九十]+、)'
    parts = re.split(pattern, text)
    sections = []
    for part in parts:
        part = part.strip()
        if len(part) < min_len:
            continue
        # 提取标题（第一行）
        lines = part.split('\n', 1)
        title = lines[0].strip()[:60]
        content = part
        sections.append((title, content))
    return sections


def _chunk_task(raw: str, level: int) -> List[Chunk]:
    """任务大纲分块：按「一、二、三…」大节分块。"""
    sections = _split_sections(raw, min_len=80)
    if not sections:
        # 没有明确分节，整段作为一个 chunk
        return [Chunk("tasks", level, f"L{level} 任务大纲", raw)]

    chunks = []
    for title, content in sections:
        chunks.append(Chunk("tasks", level, f"L{level} 任务·{title}", content))
    return chunks


def _chunk_grammar(raw: str, level: int) -> List[Chunk]:
    """语法大纲分块：按语法大类（词类、短语、句型等）分块。"""
    sections = _split_sections(raw, min_len=60)
    if not sections:
        return [Chunk("grammar", level, f"L{level} 语法大纲", raw)]

    chunks = []
    for title, content in sections:
        chunks.append(Chunk("grammar", level, f"L{level} 语法·{title}", content))
    return chunks


def _chunk_topics(raw: str, level: int) -> List[Chunk]:
    """话题大纲分块：按一级话题分块。"""
    if not raw.strip():
        return []

    # 话题大纲格式：一级话题 → 二级话题 → 三级话题
    # 按一级话题分块
    pattern = r'(?=\n?[一二三四五六七八九十]+[、.．])'
    parts = re.split(pattern, raw)
    if len(parts) <= 1:
        return [Chunk("topics", level, f"L{level} 话题大纲", raw)]

    chunks = []
    for part in parts:
        part = part.strip()
        if len(part) < 20:
            continue
        title = part.split('\n', 1)[0].strip()[:40]
        chunks.append(Chunk("topics", level, f"L{level} 话题·{title}", part))
    return chunks


def _chunk_grammar_examples(level: int) -> List[Chunk]:
    """语法例句按语法点分块。"""
    examples = get_grammar_examples(level)
    chunks = []
    for item in examples:
        point = item.get("point", "")
        examples_text = item.get("examples", "")
        content = f"【{point}】\n{examples_text}"
        chunks.append(Chunk("grammar_examples", level, f"L{level} 例句·{point}", content))
    return chunks


# ── TF-IDF 检索引擎 ──────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """jieba 分词，过滤停用词和标点。"""
    words = jieba.lcut(text)
    # 过滤单字停用词、标点、空白
    stop = set("的了在是我你他她它们这那一二三四五六七八九十不也有和与及或")
    return [w for w in words if len(w) > 1 and w not in stop and not re.match(r'^[\s\W]+$', w)]


def _tfidf_vector(tokens: List[str], idf: Dict[str, float]) -> Dict[str, float]:
    """计算 TF-IDF 向量。"""
    tf = Counter(tokens)
    total = len(tokens) if tokens else 1
    return {w: (c / total) * idf.get(w, 1.0) for w, c in tf.items()}


def _cosine_sim(v1: Dict[str, float], v2: Dict[str, float]) -> float:
    """余弦相似度。"""
    common = set(v1) & set(v2)
    if not common:
        return 0.0
    dot = sum(v1[k] * v2[k] for k in common)
    norm1 = math.sqrt(sum(x * x for x in v1.values()))
    norm2 = math.sqrt(sum(x * x for x in v2.values()))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class SyllabusIndex:
    """考纲 RAG 索引。

    构建时对所有考纲分块做 jieba 分词 + TF-IDF 索引。
    查询时返回与用户消息最相关的 top-K 块。
    """

    def __init__(self, level: int, top_k: int = 8):
        self.level = level
        self.top_k = top_k
        self.chunks: List[Chunk] = []
        self._idf: Dict[str, float] = {}
        self._chunk_vectors: List[Dict[str, float]] = []
        self._build()

    def _build(self):
        """构建索引。"""
        s = get_syllabus(self.level)

        # 收集所有块
        self.chunks = []
        self.chunks.extend(_chunk_task(s.tasks, self.level))
        self.chunks.extend(_chunk_grammar(s.grammar, self.level))
        self.chunks.extend(_chunk_topics(s.topics, self.level))
        self.chunks.extend(_chunk_grammar_examples(self.level))

        # 分词
        all_doc_tokens: List[List[str]] = []
        for chunk in self.chunks:
            tokens = _tokenize(chunk.content)
            # dataclass frozen=True，需要 object.__setattr__
            object.__setattr__(chunk, 'tokens', tokens)
            all_doc_tokens.append(tokens)

        # 计算 IDF
        df: Counter = Counter()
        for tokens in all_doc_tokens:
            for w in set(tokens):
                df[w] += 1
        n_docs = len(all_doc_tokens) if all_doc_tokens else 1
        self._idf = {w: math.log((n_docs + 1) / (c + 1)) + 1 for w, c in df.items()}

        # 计算每个块的 TF-IDF 向量
        self._chunk_vectors = [_tfidf_vector(t, self._idf) for t in all_doc_tokens]

    def retrieve(self, query: str) -> List[Chunk]:
        """根据查询返回最相关的块。"""
        if not self.chunks:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            # 查询太短，返回任务大纲的前几块
            return [c for c in self.chunks if c.category == "tasks"][:self.top_k]

        query_vec = _tfidf_vector(query_tokens, self._idf)

        # 计算相似度
        scored: List[Tuple[float, int]] = []
        for i, chunk_vec in enumerate(self._chunk_vectors):
            sim = _cosine_sim(query_vec, chunk_vec)
            scored.append((sim, i))

        # 排序取 top-K
        scored.sort(reverse=True)
        results = []
        seen_categories = set()
        for sim, idx in scored[:self.top_k * 2]:  # 多取一些，去重后截断
            if sim < 0.01:
                continue
            chunk = self.chunks[idx]
            # 确保每个类别至少有一个块
            results.append(chunk)
            seen_categories.add(chunk.category)
            if len(results) >= self.top_k:
                break

        # 确保至少有一些结果
        if not results:
            # fallback: 返回任务大纲的第一个块
            for c in self.chunks:
                if c.category == "tasks":
                    results.append(c)
                    break

        return results[:self.top_k]


# ── 缓存 ─────────────────────────────────────────────────────

_index_cache: Dict[Tuple[int, int], SyllabusIndex] = {}


def get_syllabus_index(level: int, top_k: int = 8) -> SyllabusIndex:
    """获取考纲索引（带缓存）。"""
    key = (level, top_k)
    if key not in _index_cache:
        _index_cache[key] = SyllabusIndex(level, top_k)
    return _index_cache[key]


def retrieve_syllabus(query: str, level: int, top_k: int = 8) -> str:
    """检索与查询最相关的考纲内容，返回拼接后的文本。"""
    index = get_syllabus_index(level, top_k)
    chunks = index.retrieve(query)

    if not chunks:
        return ""

    parts = []
    for chunk in chunks:
        parts.append(f"── {chunk.title} ──\n{chunk.content}")

    return "\n\n".join(parts)
