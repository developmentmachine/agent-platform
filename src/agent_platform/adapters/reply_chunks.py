"""将长回复拆成多条 IM 消息，避免在 adapter 层截断丢失正文。"""
from __future__ import annotations


def split_reply_chunks(text: str, *, max_chars: int) -> list[str]:
    """按段落/行优先切分，保证每段不超过 ``max_chars``，且不丢弃任何字符。"""
    text = text.strip()
    if not text:
        return []
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")

    chunks: list[str] = []
    remaining = text
    while remaining:
        piece = _take_chunk(remaining, max_chars=max_chars)
        if not piece:
            piece = remaining[:max_chars]
        chunks.append(piece)
        remaining = remaining[len(piece) :]

    if len(chunks) > 1:
        total = len(chunks)
        chunks = [
            f"【{i}/{total}】\n{c}" if i > 1 else c for i, c in enumerate(chunks, start=1)
        ]
    return chunks


def _take_chunk(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    window = text[: max_chars + 1]
    for sep in ("\n\n", "\n", "。"):
        idx = window.rfind(sep)
        if idx > max_chars // 4:
            return text[: idx + len(sep)].rstrip()
    return text[:max_chars]


__all__ = ["split_reply_chunks"]
