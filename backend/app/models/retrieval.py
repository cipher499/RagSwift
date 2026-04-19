from typing import Literal

from pydantic import BaseModel


class Hit(BaseModel):
    chunk_id: str                # "<document_id>:<zero-padded-index>"
    document_id: str
    filename: str
    chunk_index: int
    text: str                    # full chunk text
    source_page: int | None
    score: float                 # cosine similarity in [0, 1]
    source: Literal["semantic"]  # Phase 1: always "semantic"


class RewriteResult(BaseModel):
    original_query: str
    rewritten_query: str
    is_noop: bool                # True if rewritten == original (stripped, lowercased)
    rewrite_fallback: bool = False  # True only when rewrite() caught an exception


class RetrievalResult(BaseModel):
    semantic_hits: list[Hit]     # may be empty on semantic_fallback
    flags: dict[str, bool]       # rewrite_fallback, semantic_fallback
