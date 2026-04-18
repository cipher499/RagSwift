import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class DocumentStatus(str, Enum):
    pending = "pending"
    parsing = "parsing"
    chunking = "chunking"
    embedding = "embedding"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"


class Document(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    filename: str
    content_hash: str
    mime_type: str
    size_bytes: int
    num_pages: Optional[int] = None
    num_chunks: int = 0
    status: DocumentStatus = DocumentStatus.pending
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class IngestionEvent(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    document_id: str = Field(foreign_key="document.id", index=True)
    step: str   # upload | parse | chunk | embed | index
    state: str  # running | complete | failed
    progress_pct: int
    message: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
