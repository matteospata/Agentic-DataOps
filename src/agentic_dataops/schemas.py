from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ColumnProfile(BaseModel):
    name: str
    inferred_type: Literal["integer", "number", "boolean", "date", "string", "unknown"]
    row_count: int
    null_count: int
    unique_count: int
    sample_values: list[str] = Field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None


class DatasetInfo(BaseModel):
    name: str
    path: str
    format: str
    row_count: int
    columns: list[str]
    inferred_types: dict[str, str]
    size_bytes: int


class DataQualityIssue(BaseModel):
    severity: Literal["info", "warning", "critical"]
    rule: str
    message: str
    column: str | None = None


class DataProfile(BaseModel):
    dataset: DatasetInfo
    columns: list[ColumnProfile]
    duplicate_row_count: int
    issues: list[DataQualityIssue]


class QueryResult(BaseModel):
    dataset: str
    query: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool = False


class KnowledgeResult(BaseModel):
    source: str
    title: str
    text: str
    score: float


class AgentRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4_000)
    dataset: str | None = None


class AgentRun(BaseModel):
    run_id: str
    question: str
    dataset: str | None = None
    status: Literal["running", "completed", "failed"] = "running"
    answer: str | None = None
    profile: DataProfile | None = None
    query_result: QueryResult | None = None
    knowledge: list[KnowledgeResult] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

