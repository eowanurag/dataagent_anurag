"""Request/response models for investigation/runs/audit/export."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    user_id: str
    display_name: str | None = None
    rank: str | None = None
    unit: str | None = None


class FileUploadResponse(BaseModel):
    file_id: str
    investigation_id: str
    filename: str
    content_type: str
    size_bytes: int
    row_count: int | None = None
    columns: list[str] | None = None


class InvestigationCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    tags: list[str] | None = None


class InvestigationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    tags: list[str] | None = None


class InvestigationOut(BaseModel):
    investigation_id: str
    owner_user_id: str
    title: str
    description: str | None
    tags: list[str] | None
    live_source_enabled: bool
    created_at: datetime
    updated_at: datetime


class InvestigationList(BaseModel):
    items: list[InvestigationOut]
    next_cursor: str | None = None


class ChatMessageIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=20_000)


class Citation(BaseModel):
    source: str  # file name or table name
    rows: int | None = None
    sql: str | None = None
    latency_ms: int | None = None


class ChatRunResult(BaseModel):
    run_id: str
    investigation_id: str
    status: str
    question: str
    source: str | None
    answer_text: str | None
    chart_spec: dict[str, Any] | None
    citations: list[Citation]
    sql: str | None = None
    sql_row_count: int | None = None
    followup_suggestions: list[str] | None = None
    error_message: str | None = None
    provider: str | None = None
    model: str | None = None
    created_at: datetime
    latency_ms: int | None = None


class AuditOut(BaseModel):
    audit_id: str
    investigation_id: str
    run_id: str | None
    actor_user_id: str
    actor_unit: str | None
    actor_rank: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    source: str | None
    sql: str | None
    row_count: int | None
    latency_ms: int | None
    error_message: str | None
    metadata: dict[str, Any] | None
    created_at: datetime


class LiveSourceConnection(BaseModel):
    connection_name: str
    server: str
    database: str
    allowed_schemas: list[str] | None = None


class LiveSourceConnectionOut(LiveSourceConnection):
    connection_id: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
