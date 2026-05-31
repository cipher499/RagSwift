"""BM25 retriever — Phase 2.

Module-level singleton wrapping rank_bm25.BM25Okapi.
Tokenizer: re.findall(r"\\b\\w+\\b", text.lower()) for both corpus and query.

Public API:
  rebuild(nodes)            — full rebuild from ingested TextNodes
  bm25_search(query, top_k) — synchronous BM25 search; raises RetrievalError on failure
"""

import logging
import re
from typing import Optional

from rank_bm25 import BM25Okapi

from app.errors import RetrievalError
from app.models.retrieval import Hit
from app.retrieval.constants import BM25_TOP_K

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\b\w+\b")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


# ---------------------------------------------------------------------------
# Module-level singleton state
# ---------------------------------------------------------------------------

_bm25: Optional[BM25Okapi] = None
_nodes: list = []   # parallel list of TextNode objects (from LlamaIndex)


def rebuild(nodes: list) -> None:
    """Full rebuild of the BM25 index from *nodes* (list of LlamaIndex TextNode).

    Replaces any existing index.  Called after every ingestion run.
    Thread-safety: single-threaded FastAPI; no lock needed.
    """
    global _bm25, _nodes

    if not nodes:
        logger.warning("bm25.rebuild: called with empty node list — index cleared")
        _bm25 = None
        _nodes = []
        return

    corpus = [_tokenize(node.text) for node in nodes]
    _bm25 = BM25Okapi(corpus)
    _nodes = list(nodes)
    logger.info("bm25.rebuild: indexed %d nodes", len(_nodes))


def bm25_search(query: str, top_k: int = BM25_TOP_K) -> list[Hit]:
    """Return the top-k BM25 hits for *query*.

    - source="bm25", score=raw_bm25_score (float).
    - Empty index → returns [].
    - Any exception → raises RetrievalError("bm25 search failed").
    """
    if _bm25 is None or not _nodes:
        logger.warning("bm25_search: index is empty — returning []")
        return []

    try:
        tokens = _tokenize(query)
        scores: list[float] = _bm25.get_scores(tokens).tolist()

        # Pair (score, node) and sort descending; take top_k
        ranked = sorted(
            zip(scores, _nodes),
            key=lambda x: x[0],
            reverse=True,
        )[:top_k]

        hits: list[Hit] = []
        for score, node in ranked:
            meta = node.metadata or {}
            hits.append(
                Hit(
                    chunk_id=node.node_id,
                    document_id=meta.get("document_id", ""),
                    filename=meta.get("filename", ""),
                    chunk_index=int(meta.get("chunk_index", 0)),
                    text=node.text,
                    source_page=meta.get("source_page"),
                    score=float(score),
                    source="bm25",
                )
            )

        logger.info(
            "bm25_search: done query=%r num_hits=%d top_score=%.4f",
            query,
            len(hits),
            hits[0].score if hits else 0.0,
        )
        return hits

    except Exception as exc:
        logger.error("bm25_search: failed: %s", exc, exc_info=True)
        raise RetrievalError("bm25 search failed") from exc


def rebuild_from_chroma(chroma_path: str, collection_name: str = "rag_stage1") -> int:
    """Load all chunks from Chroma and rebuild the BM25 index.

    Returns the number of nodes indexed.  Safe to call at startup and after
    every ingestion run.  Returns 0 (and clears the index) if the collection
    is empty or missing.
    """
    import chromadb
    from llama_index.core.schema import TextNode

    try:
        client = chromadb.PersistentClient(path=chroma_path)
        collection = client.get_collection(name=collection_name)
    except Exception as exc:
        logger.warning("rebuild_from_chroma: collection not found (%s) — index cleared", exc)
        rebuild([])
        return 0

    result = collection.get(include=["documents", "metadatas"])
    ids: list[str] = result.get("ids") or []
    documents: list[str] = result.get("documents") or []
    metadatas: list[dict] = result.get("metadatas") or []

    if not ids:
        logger.info("rebuild_from_chroma: collection empty — index cleared")
        rebuild([])
        return 0

    nodes = [
        TextNode(id_=id_, text=text or "", metadata=meta or {})
        for id_, text, meta in zip(ids, documents, metadatas)
    ]
    rebuild(nodes)
    logger.info("rebuild_from_chroma: indexed %d chunks from collection '%s'", len(nodes), collection_name)
    return len(nodes)
