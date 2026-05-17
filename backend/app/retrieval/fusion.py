"""RRF (Reciprocal Rank Fusion) — Phase 3.

fuse(bm25_hits, semantic_hits, k, top_k) -> list[Hit]

RRF formula: score(chunk) += 1 / (k + rank + 1), rank 0-indexed.
Accumulate across both lists.  Deduplicate by chunk_id.
"""

import logging

from app.models.retrieval import Hit
from app.retrieval.constants import FUSED_TOP_K, RRF_K

logger = logging.getLogger(__name__)


def fuse(
    bm25_hits: list[Hit],
    semantic_hits: list[Hit],
    k: int = RRF_K,
    top_k: int = FUSED_TOP_K,
) -> list[Hit]:
    """Combine *bm25_hits* and *semantic_hits* with Reciprocal Rank Fusion.

    - Both empty  → [].
    - Single non-empty list → fuse over that list only (valid RRF scores).
    - Output: top *top_k* by fused score desc.
      source="fused", score=rrf_score, rrf_score=rrf_score.
      bm25_rank / semantic_rank set to 0-indexed rank, None if absent.
    """
    if not bm25_hits and not semantic_hits:
        logger.warning("fuse: both hit lists are empty — returning []")
        return []

    # Build lookup: chunk_id → Hit prototype (prefer semantic for metadata)
    chunk_meta: dict[str, Hit] = {}
    rrf_scores: dict[str, float] = {}
    bm25_ranks: dict[str, int] = {}
    semantic_ranks: dict[str, int] = {}

    for rank, hit in enumerate(bm25_hits):
        chunk_meta[hit.chunk_id] = hit
        rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank + 1)
        bm25_ranks[hit.chunk_id] = rank

    for rank, hit in enumerate(semantic_hits):
        if hit.chunk_id not in chunk_meta:
            chunk_meta[hit.chunk_id] = hit
        rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank + 1)
        semantic_ranks[hit.chunk_id] = rank

    # Sort by RRF score descending, take top_k
    sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)[:top_k]

    fused: list[Hit] = []
    for cid in sorted_ids:
        proto = chunk_meta[cid]
        rrf_score = rrf_scores[cid]
        fused.append(
            Hit(
                chunk_id=proto.chunk_id,
                document_id=proto.document_id,
                filename=proto.filename,
                chunk_index=proto.chunk_index,
                text=proto.text,
                source_page=proto.source_page,
                score=rrf_score,
                source="fused",
                rrf_score=rrf_score,
                bm25_rank=bm25_ranks.get(cid),
                semantic_rank=semantic_ranks.get(cid),
            )
        )

    logger.info(
        "fuse: bm25=%d semantic=%d → fused=%d top_rrf=%.6f",
        len(bm25_hits),
        len(semantic_hits),
        len(fused),
        fused[0].rrf_score if fused else 0.0,
    )
    return fused
