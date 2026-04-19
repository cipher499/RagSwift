"""Phase 1 retrieval orchestrator.

Pipeline: query → rewrite → semantic_search → RetrievalResult

Fallback rules (CLAUDE.md §10 / specs/retrieval.md §4):
  - rewrite fails  → use original query, rewrite_fallback=True in flags, log WARNING
  - semantic fails → empty hits, semantic_fallback=True in flags, log WARNING
Both fallbacks are visible in RetrievalResult.flags — never silent.
"""

import logging

from app.models.retrieval import RetrievalResult
from app.retrieval.rewrite import rewrite
from app.retrieval.semantic import semantic_search

logger = logging.getLogger(__name__)


async def retrieve(query: str) -> RetrievalResult:
    """Run the Phase 1 retrieval pipeline for *query*.

    Returns a RetrievalResult with semantic_hits and merged flags from
    both the rewrite and semantic steps.
    """
    logger.info("retrieve: start query=%r", query)
    flags: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Step 1 — Rewrite
    # rewrite() never raises: it handles its own exceptions and signals
    # fallback via RewriteResult.rewrite_fallback.
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
    # Step 2 — Semantic search
    # ------------------------------------------------------------------
    try:
        hits = await semantic_search(effective_query, top_k=10)
        logger.info("retrieve: semantic done num_hits=%d", len(hits))
    except Exception as exc:
        logger.warning("retrieve: semantic_fallback triggered: %s", exc, exc_info=True)
        flags["semantic_fallback"] = True
        return RetrievalResult(semantic_hits=[], flags=flags)

    return RetrievalResult(semantic_hits=hits, flags=flags)
