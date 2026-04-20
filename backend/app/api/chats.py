"""Chat endpoints: CRUD + SSE message streaming."""

import json
import logging
import time
import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.db import engine
from app.errors import RetrievalError
from app.generation.generate import CANNED_MESSAGE, generate
from app.models.chat import Chat, Message, MessageRole, Trace
from app.models.document import Document, DocumentStatus
from app.retrieval.rewrite import rewrite
from app.retrieval.semantic import semantic_search

router = APIRouter(prefix="/api/chats")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evt(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data)}


def _error(status: int, code: str, detail: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "detail": detail})


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


# ---------------------------------------------------------------------------
# POST /api/chats
# ---------------------------------------------------------------------------

@router.post("", status_code=201)
def create_chat():
    with Session(engine) as session:
        chat = Chat()
        session.add(chat)
        session.commit()
        session.refresh(chat)
        return chat.model_dump(mode="json")


# ---------------------------------------------------------------------------
# GET /api/chats
# ---------------------------------------------------------------------------

@router.get("")
def list_chats():
    with Session(engine) as session:
        chats = session.exec(
            select(Chat).order_by(Chat.updated_at.desc())
        ).all()
        return {"chats": [c.model_dump(mode="json") for c in chats]}


# ---------------------------------------------------------------------------
# GET /api/chats/{chat_id}
# ---------------------------------------------------------------------------

@router.get("/{chat_id}")
def get_chat(chat_id: str):
    with Session(engine) as session:
        chat = session.get(Chat, chat_id)
        if chat is None:
            return _error(404, "chat_not_found")
        messages = session.exec(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at)
        ).all()
        return {
            "chat": chat.model_dump(mode="json"),
            "messages": [m.model_dump(mode="json") for m in messages],
        }


# ---------------------------------------------------------------------------
# DELETE /api/chats/{chat_id}
# ---------------------------------------------------------------------------

@router.delete("/{chat_id}", status_code=204)
def delete_chat(chat_id: str):
    with Session(engine) as session:
        chat = session.get(Chat, chat_id)
        if chat is None:
            return _error(404, "chat_not_found")

        # Manual cascade: Traces → Messages → Chat
        for trace in session.exec(select(Trace).where(Trace.chat_id == chat_id)).all():
            session.delete(trace)
        for msg in session.exec(select(Message).where(Message.chat_id == chat_id)).all():
            session.delete(msg)
        session.delete(chat)
        session.commit()

    return Response(status_code=204)


# ---------------------------------------------------------------------------
# POST /api/chats/{chat_id}/messages  (SSE)
# ---------------------------------------------------------------------------

@router.post("/{chat_id}/messages")
async def send_message(chat_id: str, request: MessageRequest):
    content = request.content.strip()
    if not content:
        return _error(400, "empty_message", "Message content cannot be empty")

    # Pre-stream checks (return regular HTTP errors before opening SSE stream)
    with Session(engine) as session:
        chat = session.get(Chat, chat_id)
        if chat is None:
            return _error(404, "chat_not_found")

    with Session(engine) as session:
        ready_count = session.exec(
            select(func.count()).select_from(Document).where(
                Document.status == DocumentStatus.ready
            )
        ).one()
        if ready_count == 0:
            return _error(400, "no_documents_ready", "No documents are ready for querying")

    async def event_generator():
        start_time = time.monotonic()
        full_answer = ""

        try:
            # Load chat history BEFORE saving the user message
            with Session(engine) as session:
                history_limit = settings.chat_history_turns * 2
                history_rows = session.exec(
                    select(Message)
                    .where(Message.chat_id == chat_id)
                    .order_by(Message.created_at.desc())
                    .limit(history_limit)
                ).all()
                # Oldest first; detach from session by reading into plain list
                history_messages = list(reversed(history_rows))

            # Save user message
            with Session(engine) as session:
                user_msg = Message(
                    chat_id=chat_id,
                    role=MessageRole.user,
                    content=content,
                )
                session.add(user_msg)
                session.commit()
                session.refresh(user_msg)
                user_message_id = user_msg.id

            yield _evt("user_message_saved", {"message_id": user_message_id, "chat_id": chat_id})

            # Rewrite (never raises — falls back to original on exception)
            rewrite_result = await rewrite(content)
            yield _evt("trace_partial", {"rewritten_query": rewrite_result.rewritten_query})

            # Semantic search
            semantic_fallback = False
            hits = []
            try:
                hits = await semantic_search(rewrite_result.rewritten_query, settings.semantic_top_k)
            except RetrievalError:
                semantic_fallback = True
                logger.warning("send_message: semantic_search failed, using empty hits")

            yield _evt("trace_partial", {"semantic_hits": [h.model_dump() for h in hits]})

            flags = {
                "rewrite_fallback": rewrite_result.rewrite_fallback,
                "semantic_fallback": semantic_fallback,
            }

            # Generate and stream tokens
            async for token in generate(content, hits, history_messages):
                full_answer += token
                yield _evt("token", {"text": token})

            # Persist assistant message + trace
            latency_ms = int((time.monotonic() - start_time) * 1000)
            trace_id = str(uuid.uuid4())

            with Session(engine) as session:
                asst_msg = Message(
                    chat_id=chat_id,
                    role=MessageRole.assistant,
                    content=full_answer,
                    trace_id=trace_id,
                )
                session.add(asst_msg)

                trace = Trace(
                    id=trace_id,
                    chat_id=chat_id,
                    original_query=content,
                    rewritten_query=rewrite_result.rewritten_query,
                    semantic_hits_json=json.dumps([h.model_dump() for h in hits]),
                    final_answer=full_answer,
                    latency_ms=latency_ms,
                    flags_json=json.dumps(flags),
                )
                session.add(trace)

                chat_row = session.get(Chat, chat_id)
                if chat_row:
                    chat_row.updated_at = _utcnow()

                session.commit()
                session.refresh(asst_msg)
                asst_msg_id = asst_msg.id

            yield _evt("done", {
                "message_id": asst_msg_id,
                "trace_id": trace_id,
                "latency_ms": latency_ms,
            })

        except Exception as exc:
            logger.error("send_message: unexpected error: %s", exc, exc_info=True)
            yield _evt("error", {"error": "internal_error", "detail": str(exc)})

    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        ping=15,
    )


# ---------------------------------------------------------------------------
# GET /api/chats/{chat_id}/traces/{trace_id}
# ---------------------------------------------------------------------------

@router.get("/{chat_id}/traces/{trace_id}")
def get_trace(chat_id: str, trace_id: str):
    with Session(engine) as session:
        trace = session.get(Trace, trace_id)
        if trace is None or trace.chat_id != chat_id:
            return _error(404, "trace_not_found")

        return {
            "id": trace.id,
            "chat_id": trace.chat_id,
            "original_query": trace.original_query,
            "rewritten_query": trace.rewritten_query,
            "semantic_hits": json.loads(trace.semantic_hits_json),
            "final_answer": trace.final_answer,
            "latency_ms": trace.latency_ms,
            "langsmith_run_url": trace.langsmith_run_url,
            "flags": json.loads(trace.flags_json),
            "created_at": trace.created_at.isoformat(),
        }
