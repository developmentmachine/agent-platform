import re

from agent_platform.adapters.reply_chunks import split_reply_chunks

_PART_RE = re.compile(r"^【\d+/\d+】\n")


def _strip_part_headers(chunks: list[str]) -> str:
    out: list[str] = []
    for c in chunks:
        out.append(_PART_RE.sub("", c, count=1))
    return "".join(out)


def test_split_empty() -> None:
    assert split_reply_chunks("", max_chars=100) == []
    assert split_reply_chunks("   ", max_chars=100) == []


def test_split_short_unchanged() -> None:
    assert split_reply_chunks("hello", max_chars=100) == ["hello"]


def test_split_preserves_all_chars() -> None:
    text = "段落一\n\n" + "中" * 500 + "\n\n段落二\n\n" + "末" * 300
    chunks = split_reply_chunks(text, max_chars=200)
    assert len(chunks) >= 2
    restored = _strip_part_headers(chunks)
    assert restored == text
    assert "段落一" in chunks[0]


def test_split_hard_break_when_no_separator() -> None:
    text = "x" * 500
    chunks = split_reply_chunks(text, max_chars=200)
    assert len(chunks) == 3
    assert _strip_part_headers(chunks) == text
