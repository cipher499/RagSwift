"""Isolation tests for RRF fusion (Phase 2, Step 5).

Run with: pytest backend/tests/test_fusion.py -v
(No external dependencies required.)
"""

from app.models.retrieval import Hit
from app.retrieval.fusion import fuse
from app.retrieval.constants import RRF_K, FUSED_TOP_K


def _hit(chunk_id: str, score: float = 1.0, source: str = "semantic") -> Hit:
    return Hit(
        chunk_id=chunk_id,
        document_id="doc1",
        filename="test.txt",
        chunk_index=0,
        text="dummy text",
        source_page=None,
        score=score,
        source=source,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# 1. Overlapping chunks score higher than single-list chunks
# ---------------------------------------------------------------------------

def test_overlapping_chunks_score_higher():
    bm25_hits = [_hit("A", source="bm25"), _hit("B", source="bm25"), _hit("C", source="bm25")]
    sem_hits  = [_hit("A", source="semantic"), _hit("D", source="semantic")]

    result = fuse(bm25_hits, sem_hits)

    # chunk A appears in both lists → highest fused score
    assert result[0].chunk_id == "A", f"expected A first, got {result[0].chunk_id}"
    a_score = result[0].rrf_score
    others = [h.rrf_score for h in result if h.chunk_id != "A"]
    assert all(a_score > s for s in others), "A should outscore all single-list chunks"


# ---------------------------------------------------------------------------
# 2. Fused scores are in the expected ~0.01–0.03 range (k=60)
# ---------------------------------------------------------------------------

def test_fused_score_range():
    bm25_hits = [_hit(f"b{i}", source="bm25") for i in range(5)]
    sem_hits  = [_hit(f"s{i}", source="semantic") for i in range(5)]

    result = fuse(bm25_hits, sem_hits)

    for h in result:
        assert h.rrf_score is not None
        assert 0.0 < h.rrf_score < 0.05, f"score {h.rrf_score} out of expected range"


# ---------------------------------------------------------------------------
# 3. bm25_rank / semantic_rank populated correctly
# ---------------------------------------------------------------------------

def test_rank_fields_populated():
    bm25_hits = [_hit("A", source="bm25"), _hit("B", source="bm25")]
    sem_hits  = [_hit("B", source="semantic"), _hit("C", source="semantic")]

    result = fuse(bm25_hits, sem_hits)
    by_id = {h.chunk_id: h for h in result}

    # A: only in BM25 (rank 0) → bm25_rank=0, semantic_rank=None
    assert by_id["A"].bm25_rank == 0
    assert by_id["A"].semantic_rank is None

    # B: rank 1 in BM25, rank 0 in semantic
    assert by_id["B"].bm25_rank == 1
    assert by_id["B"].semantic_rank == 0

    # C: only in semantic (rank 1) → semantic_rank=1, bm25_rank=None
    assert by_id["C"].semantic_rank == 1
    assert by_id["C"].bm25_rank is None


# ---------------------------------------------------------------------------
# 4. Single-list fusion works (only BM25, only semantic)
# ---------------------------------------------------------------------------

def test_single_list_bm25_only():
    bm25_hits = [_hit("X", source="bm25"), _hit("Y", source="bm25")]
    result = fuse(bm25_hits, [])
    assert len(result) == 2
    assert all(h.source == "fused" for h in result)
    assert result[0].semantic_rank is None
    assert result[0].bm25_rank == 0


def test_single_list_semantic_only():
    sem_hits = [_hit("X", source="semantic"), _hit("Y", source="semantic")]
    result = fuse([], sem_hits)
    assert len(result) == 2
    assert all(h.source == "fused" for h in result)
    assert result[0].bm25_rank is None
    assert result[0].semantic_rank == 0


# ---------------------------------------------------------------------------
# 5. Both empty → []
# ---------------------------------------------------------------------------

def test_both_empty():
    assert fuse([], []) == []


# ---------------------------------------------------------------------------
# 6. top_k is respected
# ---------------------------------------------------------------------------

def test_top_k_respected():
    bm25_hits = [_hit(f"b{i}", source="bm25") for i in range(15)]
    sem_hits  = [_hit(f"s{i}", source="semantic") for i in range(15)]
    result = fuse(bm25_hits, sem_hits, top_k=5)
    assert len(result) == 5


# ---------------------------------------------------------------------------
# 7. source and score fields on output hits
# ---------------------------------------------------------------------------

def test_output_hit_fields():
    bm25_hits = [_hit("A", source="bm25")]
    sem_hits  = [_hit("A", source="semantic")]
    result = fuse(bm25_hits, sem_hits)
    h = result[0]
    assert h.source == "fused"
    assert h.score == h.rrf_score
    assert h.rrf_score is not None
