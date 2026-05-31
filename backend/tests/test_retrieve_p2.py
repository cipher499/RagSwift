"""P2 retrieval orchestrator tests — fallback paths and flag correctness.

These tests mock the BM25 and semantic backends so they can run without
a live OpenAI / Chroma connection.

Run with: pytest backend/tests/test_retrieve_p2.py -v
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.errors import RetrievalError
from app.models.retrieval import Hit, RetrievalResult


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _hit(chunk_id: str, source: str = "semantic") -> Hit:
    return Hit(
        chunk_id=chunk_id,
        document_id="doc1",
        filename="f.txt",
        chunk_index=0,
        text="text",
        source_page=None,
        score=0.9,
        source=source,  # type: ignore[arg-type]
    )


_SEM_HITS  = [_hit("A", "semantic"), _hit("B", "semantic")]
_BM25_HITS = [_hit("A", "bm25"),     _hit("C", "bm25")]


def _make_rewrite_result(query: str, fallback: bool = False):
    from app.models.retrieval import RewriteResult
    return RewriteResult(
        original_query=query,
        rewritten_query=query,
        is_noop=True,
        rewrite_fallback=fallback,
    )


# ---------------------------------------------------------------------------
# 1. Happy path — both BM25 and semantic succeed → fused result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_both_succeed_returns_fused():
    with (
        patch("app.retrieval.retrieve.rewrite", new=AsyncMock(return_value=_make_rewrite_result("q"))),
        patch("app.retrieval.retrieve.bm25_search", return_value=_BM25_HITS),
        patch("app.retrieval.retrieve.semantic_search", new=AsyncMock(return_value=_SEM_HITS)),
    ):
        from app.retrieval.retrieve import retrieve
        result = await retrieve("q")

    assert isinstance(result, RetrievalResult)
    assert len(result.bm25_hits) == len(_BM25_HITS)
    assert len(result.semantic_hits) == len(_SEM_HITS)
    assert len(result.fused_hits) > 0
    assert result.flags == {}


# ---------------------------------------------------------------------------
# 2. BM25 fails → bm25_fallback=True, fuse over semantic only
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bm25_fails_semantic_only():
    with (
        patch("app.retrieval.retrieve.rewrite", new=AsyncMock(return_value=_make_rewrite_result("q"))),
        patch("app.retrieval.retrieve.bm25_search", side_effect=RetrievalError("bm25 search failed")),
        patch("app.retrieval.retrieve.semantic_search", new=AsyncMock(return_value=_SEM_HITS)),
    ):
        from app.retrieval.retrieve import retrieve
        result = await retrieve("q")

    assert result.flags.get("bm25_fallback") is True
    assert "semantic_fallback" not in result.flags
    assert result.bm25_hits == []
    assert len(result.semantic_hits) == len(_SEM_HITS)
    # fuse over semantic only → still produces hits
    assert len(result.fused_hits) > 0
    for h in result.fused_hits:
        assert h.bm25_rank is None


# ---------------------------------------------------------------------------
# 3. Semantic fails → semantic_fallback=True, fuse over BM25 only
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_fails_bm25_only():
    with (
        patch("app.retrieval.retrieve.rewrite", new=AsyncMock(return_value=_make_rewrite_result("q"))),
        patch("app.retrieval.retrieve.bm25_search", return_value=_BM25_HITS),
        patch("app.retrieval.retrieve.semantic_search", new=AsyncMock(side_effect=RetrievalError("semantic search failed"))),
    ):
        from app.retrieval.retrieve import retrieve
        result = await retrieve("q")

    assert result.flags.get("semantic_fallback") is True
    assert "bm25_fallback" not in result.flags
    assert result.semantic_hits == []
    assert len(result.bm25_hits) == len(_BM25_HITS)
    assert len(result.fused_hits) > 0
    for h in result.fused_hits:
        assert h.semantic_rank is None


# ---------------------------------------------------------------------------
# 4. Both fail → both flags True, fused_hits=[]
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_both_fail_empty_fused():
    with (
        patch("app.retrieval.retrieve.rewrite", new=AsyncMock(return_value=_make_rewrite_result("q"))),
        patch("app.retrieval.retrieve.bm25_search", side_effect=RetrievalError("bm25 search failed")),
        patch("app.retrieval.retrieve.semantic_search", new=AsyncMock(side_effect=RetrievalError("semantic search failed"))),
    ):
        from app.retrieval.retrieve import retrieve
        result = await retrieve("q")

    assert result.flags.get("bm25_fallback") is True
    assert result.flags.get("semantic_fallback") is True
    assert result.bm25_hits == []
    assert result.semantic_hits == []
    assert result.fused_hits == []


# ---------------------------------------------------------------------------
# 5. Rewrite fails → rewrite_fallback=True, pipeline continues with original
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rewrite_fallback_pipeline_continues():
    with (
        patch("app.retrieval.retrieve.rewrite", new=AsyncMock(return_value=_make_rewrite_result("q", fallback=True))),
        patch("app.retrieval.retrieve.bm25_search", return_value=_BM25_HITS),
        patch("app.retrieval.retrieve.semantic_search", new=AsyncMock(return_value=_SEM_HITS)),
    ):
        from app.retrieval.retrieve import retrieve
        result = await retrieve("q")

    assert result.flags.get("rewrite_fallback") is True
    assert len(result.fused_hits) > 0   # pipeline still runs


# ---------------------------------------------------------------------------
# 6. fused_hits scores ~0.01–0.03 (from real fusion on real hit objects)
# ---------------------------------------------------------------------------

def test_fused_scores_in_range():
    from app.retrieval.fusion import fuse
    bm25  = [_hit(f"b{i}", "bm25")     for i in range(5)]
    sem   = [_hit(f"s{i}", "semantic") for i in range(5)]
    fused = fuse(bm25, sem)
    for h in fused:
        assert 0.0 < h.rrf_score < 0.05


# ---------------------------------------------------------------------------
# 7. Overlapping chunk scores higher in fused list
# ---------------------------------------------------------------------------

def test_overlap_chunk_scores_highest():
    from app.retrieval.fusion import fuse
    bm25 = [_hit("SHARED", "bm25"), _hit("B_only", "bm25")]
    sem  = [_hit("SHARED", "semantic"), _hit("S_only", "semantic")]
    fused = fuse(bm25, sem)
    assert fused[0].chunk_id == "SHARED"
