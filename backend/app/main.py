"""FastAPI application entry point.

Startup sequence (per specs/retrieval.md §6):
  1. Ensure data directories exist.
  2. Create SQLite tables.
  3. Verify OpenAI API — gpt-4o-mini and text-embedding-3-small must be available.
  4. Verify ChromaDB — heartbeat + ensure rag_stage1 collection exists.
  5. Ensure prompts/ directory exists (content added in Phase 1 retrieval).
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import chromadb
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

from app.api.documents import router as documents_router
from app.config import settings
from app.db import create_db_and_tables
from app.errors import AppException
from app.ingestion.index import COLLECTION_NAME

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup: begin")

    # 1. Directories
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
    Path("prompts").mkdir(exist_ok=True)
    logger.info("startup: directories ok")

    # 2. SQLite tables
    create_db_and_tables()
    logger.info("startup: sqlite tables ok")

    # 3. OpenAI verification
    oai = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        models_page = await oai.models.list()
        available = {m.id for m in models_page.data}
        required = {"gpt-4o-mini", "text-embedding-3-small"}
        missing = required - available
        if missing:
            raise RuntimeError(
                f"Required OpenAI model(s) not available in this account: {missing}. "
                "Per CLAUDE.md §7: STOP and resolve before continuing."
            )
        logger.info("startup: OpenAI ok — %s", required)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"OpenAI startup check failed: {exc}") from exc

    # 4. ChromaDB verification
    try:
        chroma = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        chroma.heartbeat()
        chroma.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("startup: ChromaDB ok — collection '%s' ready", COLLECTION_NAME)
    except Exception as exc:
        raise RuntimeError(f"ChromaDB startup check failed: {exc}") from exc

    logger.info("startup: complete — listening on %s:%s", settings.app_host, settings.app_port)
    yield
    logger.info("shutdown: complete")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="RAGSwift API — Phase 1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "detail": exc.detail},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(documents_router)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    from sqlmodel import Session, select, func
    from app.db import engine
    from app.models.document import Document

    chroma_ok = True
    openai_ok = True

    try:
        chroma = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        chroma.heartbeat()
    except Exception:
        chroma_ok = False

    try:
        oai = AsyncOpenAI(api_key=settings.openai_api_key)
        await oai.models.list()
    except Exception:
        openai_ok = False

    with Session(engine) as session:
        num_documents = session.exec(select(func.count()).select_from(Document)).one()

    status = "ok" if (chroma_ok and openai_ok) else "degraded"
    return {
        "status": status,
        "chroma_ok": chroma_ok,
        "openai_ok": openai_ok,
        "num_documents": num_documents,
    }
