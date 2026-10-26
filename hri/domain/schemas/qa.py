"""질의응답 스키마 · AnswerResult, SuggestOutput, SearchHit, ContextDoc (서동안)"""

"""Chunk는 보고서 스키마(3.2.1: Page·Section·Chunk·Table·Report)에서 같은 모듈에 정의한다.
이 파일의 클래스는 그 정의와 같은 domain/schemas.py에 함께 둔다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AnswerResult(BaseModel):
    """ask_stream()이 답변 조각을 모두 보낸 뒤 마지막에 넘기는 질문 1건의 결과."""

    question: str
    answer: str
    sources: list[dict] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    has_source: bool = False
    route: Literal["chat", "rewrite", "error"]
    tokens: int = 0
    cost_krw: float = 0.0
    log_id: int | None = None


class SuggestOutput(BaseModel):
    """suggest_questions()가 with_structured_output()으로 받는 후속 질문과 용어."""

    questions: list[str] = Field(
        min_length=3,
        max_length=3,
        description="질문과 답변에 이어서 물어볼 만한 후속 질문 정확히 3개",
    )
    terms: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="답변에 나온 어려운 경제 용어 최대 3개 (없으면 빈 리스트)",
    )


class SearchHit(BaseModel):
    """vector_search()의 의미 검색 결과 1건."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    chunk: Chunk
    score: float  # 관련도 = 1 - 거리
    embedding: list[float]  # mmr_select()에서 유사도 계산에 사용


class ContextDoc(BaseModel):
    """format_docs()·format_sources()에 넘기는 근거 1건."""

    report_id: int
    report_title: str
    kind: Literal["text", "table", "chart"]
    section_title: str | None = None
    caption: str | None = None
    page_start: int
    page_end: int
    text: str
    needs_review: bool = False  # 차트 OCR 추정값이면 True

