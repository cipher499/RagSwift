"""Ingestion pipeline orchestrator.

Runs parse → chunk → embed → index for a single document, writing
IngestionEvent rows to SQLite at each step so the SSE progress endpoint
can replay them to the client.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session

from app.db import engine
from app.errors import IngestionError
from app.ingestion.chunk import chunk_document
from app.ingestion.embed import embed_chunks
from app.ingestion.index import index_chunks
from app.ingestion.parse import parse_document
from app.models.document import Document, DocumentStatus, IngestionEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _emit(
    session: Session,
    document_id: str,
    step: str,
    state: str,
    progress_pct: int,
    message: str | None = None,
) -> None:
    """Insert an IngestionEvent row and commit immediately."""
    event = IngestionEvent(
        document_id=document_id,
        step=step,
        state=state,
        progress_pct=progress_pct,
        message=message,
    )
    session.add(event)
    session.commit()
    logger.debug("_emit: step=%s state=%s pct=%d", step, state, progress_pct)


def _set_status(session: Session, document_id: str, **fields) -> None:
    """Update Document fields and set updated_at."""
    doc = session.get(Document, document_id)
    if doc is None:
        logger.error("_set_status: document not found id=%s", document_id)
        return
    for key, value in fields.items():
        setattr(doc, key, value)
    doc.updated_at = datetime.now(timezone.utc)
    session.add(doc)
    session.commit()


# ---------------------------------------------------------------------------
# Public entry point — called as a FastAPI BackgroundTask
# ---------------------------------------------------------------------------

async def run_ingestion(document_id: str, file_path: Path, filename: str) -> None:
    """Run the full ingestion pipeline for one document.

    Steps: parse → chunk → embed → index
    Each step emits exactly one 'running' event and one 'complete' / 'failed'
    event.  On any failure the Document status is set to 'failed' and the
    function returns early (no exception propagated to the caller).
    """
    logger.info(
        "run_ingestion: start document_id=%s filename=%s file=%s",
        document_id,
        filename,
        file_path,
    )

    with Session(engine) as session:

        # ------------------------------------------------------------------
        # PARSE
        # ------------------------------------------------------------------
        _set_status(session, document_id, status=DocumentStatus.parsing)
        _emit(session, document_id, "parse", "running", 10)

        try:
            li_docs = await asyncio.to_thread(parse_document, file_path)
        except IngestionError as exc:
            _emit(session, document_id, "parse", "failed", 10, str(exc))
            _set_status(session, document_id, status=DocumentStatus.failed, error_message=str(exc))
            logger.error("run_ingestion: parse failed document_id=%s: %s", document_id, exc)
            return

        # Best-effort page count from LlamaIndex metadata
        num_pages: int | None = None
        page_numbers: set[int] = set()
        for doc in li_docs:
            raw = doc.metadata.get("page_label") or doc.metadata.get("page")
            if raw is not None:
                try:
                    page_numbers.add(int(raw))
                except (ValueError, TypeError):
                    pass
        if page_numbers:
            num_pages = max(page_numbers)

        _emit(
            session,
            document_id,
            "parse",
            "complete",
            30,
            f"Parsed {len(li_docs)} section(s)",
        )
        _set_status(session, document_id, num_pages=num_pages)

        # ------------------------------------------------------------------
        # CHUNK
        # ------------------------------------------------------------------
        _set_status(session, document_id, status=DocumentStatus.chunking)
        _emit(session, document_id, "chunk", "running", 30)

        try:
            nodes = await asyncio.to_thread(chunk_document, li_docs, document_id, filename)
        except IngestionError as exc:
            _emit(session, document_id, "chunk", "failed", 30, str(exc))
            _set_status(session, document_id, status=DocumentStatus.failed, error_message=str(exc))
            logger.error("run_ingestion: chunk failed document_id=%s: %s", document_id, exc)
            return

        _emit(
            session,
            document_id,
            "chunk",
            "complete",
            50,
            f"Produced {len(nodes)} chunk(s)",
        )

        # ------------------------------------------------------------------
        # EMBED
        # ------------------------------------------------------------------
        _set_status(session, document_id, status=DocumentStatus.embedding)
        _emit(session, document_id, "embed", "running", 50)

        try:
            embeddings = await embed_chunks(nodes)
        except IngestionError as exc:
            _emit(session, document_id, "embed", "failed", 50, str(exc))
            _set_status(session, document_id, status=DocumentStatus.failed, error_message=str(exc))
            logger.error("run_ingestion: embed failed document_id=%s: %s", document_id, exc)
            return

        _emit(
            session,
            document_id,
            "embed",
            "complete",
            85,
            f"Embedded {len(embeddings)} chunk(s)",
        )

        # ------------------------------------------------------------------
        # INDEX
        # ------------------------------------------------------------------
        _set_status(session, document_id, status=DocumentStatus.indexing)
        _emit(session, document_id, "index", "running", 85)

        try:
            await index_chunks(nodes, embeddings)
        except IngestionError as exc:
            _emit(session, document_id, "index", "failed", 85, str(exc))
            _set_status(session, document_id, status=DocumentStatus.failed, error_message=str(exc))
            logger.error("run_ingestion: index failed document_id=%s: %s", document_id, exc)
            return

        _emit(
            session,
            document_id,
            "index",
            "complete",
            100,
            f"Indexed {len(nodes)} chunk(s)",
        )
        _set_status(
            session,
            document_id,
            status=DocumentStatus.ready,
            num_chunks=len(nodes),
        )

    logger.info(
        "run_ingestion: complete document_id=%s num_chunks=%d num_pages=%s",
        document_id,
        len(nodes),
        num_pages,
    )
