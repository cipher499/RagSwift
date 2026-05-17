"""Phase 2 retrieval orchestrator.

Pipeline: query → rewrite → BM25 ∥ semantic → RRF fusion → RetrievalResult

Fallback hierarchy (CLAUDE.md §10 / specs/retrieval.md):
  - rewrite fails      → use original query, rewrite_fallback=True in flags
  - BM25 fails         → bm25_fallback=True, fuse over semantic only
  - semantic fails     → semantic_fallback=True, fuse over BM25 only
  - both fail          → both flags True, fused_hits=[], final context empty
All fallbacks logged at WARNING with exc_info — never silent.
"""

import asyncio
import logging
import time

from app.models.retrieval import RetrievalResult
from app.observability.langsmith import bm25_span, fusion_span
from app.retrieval.bm25 import bm25_search
from app.retrieval.constants import BM25_TOP_K, SEMANTIC_TOP_K
from app.retrieval.fusion import fuse
from app.retrieval.rewrite import rewrite
from app.retrieval.semantic import semantic_search

logger = logging.getLogger(__name__)


async def _timed(coro):
    """Run *coro*, return (result_or_exception, elapsed_ms).

    Never raises — exceptions are returned as the first element so that
    asyncio.gather can still run both branches in parallel.
    """
    t0 = time.monotonic()
    try:
        result = await coro
        return result, int((time.monotonic() - t0) * 1000)
    except Exception as exc:
        return exc, int((time.monotonic() - t0) * 1000)


async def retrieve(query: str) -> RetrievalResult:
    """Run the Phase 2 retrieval pipeline for *query*.

    Returns a RetrievalResult with semantic_hits, bm25_hits, fused_hits,
    flags, and the rewritten_query — all in one call so the caller
    (chats.py) never needs to invoke rewrite() or semantic_search() directly.
    """
    logger.info("retrieve: start query=%r", query)
    flags: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Step 1 — Rewrite (never raises; falls back internally)
    # ------------------------------------------------------------------
    rewrite_result = await rewrite(query)
    if rewrite_result.rewrite_fallback:
        flags["rewrite_fallback"] = True

    effective_query = rewrite_result.rewritten_query
    logger.info(
        "retrieve: rewrite done original=%r rewritten=%r is_noop=%s fallback=%s",
        rewrite_result.original_query,
        effective_query,
        rewrite_result.is_noop,
        rewrite_result.rewrite_fallback,
    )

    # ------------------------------------------------------------------
    # Step 2 — BM25 ∥ Semantic (concurrent, individually timed)
    # ------------------------------------------------------------------
    (bm25_result, bm25_ms), (semantic_result, _sem_ms) = await asyncio.gather(
        _timed(asyncio.to_thread(bm25_search, effective_query, BM25_TOP_K)),
        _timed(semantic_search(effective_query, SEMANTIC_TOP_K)),
    )

    bm25_hits = []
    semantic_hits = []
    bm25_fallback = False

    if isinstance(bm25_result, Exception):
        logger.warning(
            "retrieve: bm25_fallback triggered: %s", bm25_result, exc_info=bm25_result
        )
        flags["bm25_fallback"] = True
        bm25_fallback = True
    else:
        bm25_hits = bm25_result
        logger.info("retrieve: bm25 done num_hits=%d latency_ms=%d", len(bm25_hits), bm25_ms)

    if isinstance(semantic_result, Exception):
        logger.warning(
            "retrieve: semantic_fallback triggered: %s", semantic_result, exc_info=semantic_result
        )
        flags["semantic_fallback"] = True
    else:
        semantic_hits = semantic_result
        logger.info("retrieve: semantic done num_hits=%d latency_ms=%d", len(semantic_hits), _sem_ms)

    # LangSmith span: bm25
    async with bm25_span(
        num_hits=len(bm25_hits),
        latency_ms=bm25_ms,
        bm25_fallback=bm25_fallback,
    ):
        pass

    # ------------------------------------------------------------------
    # Step 3 — RRF Fusion
    # Both fail → fuse([], []) → [], generation returns canned message.
    # Single-list cases handled inside fuse().
    # ------------------------------------------------------------------
    fused_hits = fuse(bm25_hits, semantic_hits)
    logger.info("retrieve: fused num_hits=%d", len(fused_hits))

    # LangSmith span: fusion
    async with fusion_span(num_fused=len(fused_hits)):
        pass

    return RetrievalResult(
        semantic_hits=semantic_hits,
        bm25_hits=bm25_hits,
        fused_hits=fused_hits,
        flags=flags,
        rewritten_query=effective_query,
    )
