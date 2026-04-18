"""Document endpoints: upload, list, get, SSE progress."""

import asyncio
import hashlib
import logging
import uuid
from pathlib import Path

import chromadb
import pypdf
import io

from fastapi import APIRouter, BackgroundTasks, File, UploadFile
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.db import engine
from app.errors import AppException
from app.ingestion.pipeline import run_ingestion
from app.models.document import Document, DocumentStatus, IngestionEvent
from app.sse import done_event, error_event, step_event

router = APIRouter(prefix="/api/documents")
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".docx", ".md", ".txt"}
MIME_MAP = {
    ".pdf": "application/pdf",
    ".epub": "application/epub+zip",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(status: int, code: str, detail: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "detail": detail})


def _emit_upload_events(session: Session, document_id: str) -> None:
    """Store the upload running + complete events so the SSE stream can replay them."""
    for state, pct, msg in [
        ("running", 0, None),
        ("complete", 100, "File uploaded"),
    ]:
        session.add(
            IngestionEvent(
                document_id=document_id,
                step="upload",
                state=state,
                progress_pct=pct,
                message=msg,
            )
        )
    session.commit()


# ---------------------------------------------------------------------------
# POST /api/documents/upload
# ---------------------------------------------------------------------------

@router.post("/upload", status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    contents = await file.read()
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()

    # --- Validation ---
    if ext not in SUPPORTED_EXTENSIONS:
        return _error(400, "unsupported_file_type", f"Extension '{ext}' is not supported")

    if not contents:
        return _error(400, "empty_file", "Uploaded file is empty")

    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if len(contents) > max_bytes:
        return _error(400, "file_too_large", f"Max allowed size is {settings.max_file_size_mb} MB")

    if ext == ".pdf":
        try:
            reader = pypdf.PdfReader(io.BytesIO(contents))
            if len(reader.pages) > settings.max_pdf_pages:
                return _error(
                    400,
                    "pdf_too_long",
                    f"PDF has {len(reader.pages)} pages; max is {settings.max_pdf_pages}",
                )
        except Exception as exc:
            logger.warning("upload: pdf page probe failed: %s", exc)

    content_hash = hashlib.sha256(contents).hexdigest()

    with Session(engine) as session:
        # --- Duplicate handling ---
        duplicate = session.exec(
            select(Document).where(Document.content_hash == content_hash)
        ).first()

        if duplicate:
            old_id = duplicate.id
            logger.info(
                "upload: duplicate_overwrite document_id=<new> replaced=%s", old_id
            )
            # Remove old Chroma chunks
            try:
                chroma = chromadb.PersistentClient(path=settings.chroma_persist_dir)
                col = chroma.get_or_create_collection(
                    "rag_stage1", metadata={"hnsw:space": "cosine"}
                )
                col.delete(where={"document_id": old_id})
            except Exception as exc:
                logger.warning(
                    "upload: chroma cleanup failed for replaced doc %s: %s", old_id, exc
                )
            # Remove DB rows
            for ev in session.exec(
                select(IngestionEvent).where(IngestionEvent.document_id == old_id)
            ).all():
                session.delete(ev)
            session.delete(duplicate)
            session.commit()

        # --- Document limit (checked after duplicate removal) ---
        active_count = len(
            session.exec(
                select(Document).where(Document.status != DocumentStatus.failed)
            ).all()
        )
        if active_count >= settings.max_documents:
            return _error(
                400,
                "document_limit_reached",
                f"Maximum of {settings.max_documents} documents reached",
            )

        # --- Persist file ---
        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        document_id = str(uuid.uuid4())
        file_path = upload_dir / f"{document_id}{ext}"

        try:
            file_path.write_bytes(contents)
        except Exception as exc:
            logger.error("upload: storage error: %s", exc)
            return _error(500, "storage_error", str(exc))

        # --- Create Document row ---
        doc = Document(
            id=document_id,
            filename=filename,
            content_hash=content_hash,
            mime_type=MIME_MAP.get(ext, "application/octet-stream"),
            size_bytes=len(contents),
            status=DocumentStatus.pending,
        )
        session.add(doc)
        session.commit()

        # --- Store upload step events for SSE replay ---
        _emit_upload_events(session, document_id)

    # --- Kick off background ingestion ---
    background_tasks.add_task(run_ingestion, document_id, file_path, filename)
    logger.info("upload: queued document_id=%s filename=%s size=%d", document_id, filename, len(contents))

    return {"document_id": document_id, "filename": filename, "status": "pending"}


# ---------------------------------------------------------------------------
# GET /api/documents
# ---------------------------------------------------------------------------

@router.get("")
def list_documents():
    with Session(engine) as session:
        docs = session.exec(
            select(Document).order_by(Document.created_at.desc())
        ).all()
        return {"documents": [d.model_dump(mode="json") for d in docs]}


# ---------------------------------------------------------------------------
# GET /api/documents/{document_id}
# ---------------------------------------------------------------------------

@router.get("/{document_id}")
def get_document(document_id: str):
    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            return _error(404, "document_not_found")
        return doc.model_dump(mode="json")


# ---------------------------------------------------------------------------
# GET /api/documents/{document_id}/progress  (SSE)
# ---------------------------------------------------------------------------

@router.get("/{document_id}/progress")
async def document_progress(document_id: str):
    # Fast-fail if doc doesn't exist
    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            return _error(404, "document_not_found")

    async def generate():
        sent_count = 0

        while True:
            with Session(engine) as session:
                doc = session.get(Document, document_id)
                if doc is None:
                    return

                # Stream any new events not yet sent to the client
                new_events = session.exec(
                    select(IngestionEvent)
                    .where(IngestionEvent.document_id == document_id)
                    .order_by(IngestionEvent.created_at)
                    .offset(sent_count)
                ).all()

                for ev in new_events:
                    yield step_event(ev.step, ev.state, ev.progress_pct, ev.message)
                    sent_count += 1

                # Terminal states
                if doc.status == DocumentStatus.ready:
                    yield done_event(document_id, doc.num_chunks, doc.num_pages)
                    return

                if doc.status == DocumentStatus.failed:
                    failed_ev = session.exec(
                        select(IngestionEvent)
                        .where(
                            IngestionEvent.document_id == document_id,
                            IngestionEvent.state == "failed",
                        )
                        .order_by(IngestionEvent.created_at.desc())
                    ).first()
                    yield error_event(
                        failed_ev.step if failed_ev else "unknown",
                        "ingestion_failed",
                        failed_ev.message if failed_ev else "Unknown error",
                    )
                    return

            await asyncio.sleep(0.3)

    return EventSourceResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        ping=15,
    )
