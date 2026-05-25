"""HSK 3.0 Tutor 请求/响应模型（独立于 stock-recap 业务模型）。"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class TutorChatRequest(BaseModel):
    """单轮或多轮对话；``history`` 不含当前 ``message``。"""

    message: str = Field(min_length=1, description="用户本轮输入（中文或提问）")
    level: int = Field(
        default=1,
        ge=1,
        le=9,
        description="HSK 3.0 目标等级（1–9，对应三阶段九级框架）",
    )
    history: List[ChatTurn] = Field(default_factory=list)
    explain_locale: Literal["zh", "en", "both"] = Field(
        default="both",
        description="纠错/讲解所用语言",
    )


class TutorChatResponse(BaseModel):
    reply: str
    level: int
    request_id: str
    backend: Literal["llm", "stub"] = "stub"
    note: Optional[str] = None
