from typing import Literal

from pydantic import BaseModel, Field

DayType = Literal["Weekday", "Saturday", "Sunday/Holiday"]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)
    top_k: int | None = Field(default=None, ge=1, le=10)


class SourceOut(BaseModel):
    id: str
    kind: str
    source: str
    title: str
    content: str
    page: int | None = None
    row: int | None = None
    score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    intent: str
    day_type: str
    stops: list[str]
    route_no: str | None
    provider: str
    warning: str | None = None
    data: dict


class HealthResponse(BaseModel):
    status: str
    provider: str
    model: str | None
    embedding_model: str
    chunks_indexed: int
    routes: int
    stops: int


class IngestResponse(BaseModel):
    files: list[str]
    documents: int
    chunks: int
