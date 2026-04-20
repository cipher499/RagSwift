import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class Chat(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    title: str = "New chat"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"


class Message(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    chat_id: str = Field(foreign_key="chat.id", index=True)
    role: MessageRole
    content: str
    trace_id: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)


class Trace(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    chat_id: str = Field(foreign_key="chat.id", index=True)
    original_query: str
    rewritten_query: Optional[str] = None
    semantic_hits_json: str = "[]"
    final_answer: str
    latency_ms: int
    langsmith_run_url: Optional[str] = None
    flags_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)
