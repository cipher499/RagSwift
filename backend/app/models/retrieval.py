from typing import Literal

from pydantic import BaseModel


class Hit(BaseModel):
    chunk_id: str                # "<document_id>:<zero-padded-index>"
    document_id: str
    filename: str
    chunk_index: int
    text: str                    # full chunk text
    source_page: int | None
    score: float                 # cosine similarity [0,1] or RRF score
    source: Literal["semantic", "bm25", "fused", "reranked"]
    # Phase 2+ optional fields
    rrf_score: float | None = None
    bm25_rank: int | None = None      # 0-indexed rank in BM25 results
    semantic_rank: int | None = None  # 0-indexed rank in semantic results


class RewriteResult(BaseModel):
    original_query: str
    rewritten_query: str
    is_noop: bool                # True if rewritten == original (stripped, lowercased)
    rewrite_fallback: bool = False  # True only when rewrite() caught an exception


class RetrievalResult(BaseModel):
    semantic_hits: list[Hit]     # may be empty on semantic_fallback
    flags: dict[str, bool]       # rewrite_fallback, semantic_fallback, bm25_fallback
    # Phase 2+ fields
    bm25_hits: list[Hit] = []
    fused_hits: list[Hit] = []
    rewritten_query: str = ""    # exposed so callers don't need to call rewrite() separately
