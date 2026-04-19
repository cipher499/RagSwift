"""Semantic retrieval — Phase 1.

Embed the query with OpenAI SDK directly (text-embedding-3-small).
Query ChromaDB collection rag_stage1 directly with the pre-computed embedding.
Convert cosine distances [0, 2] → similarities [0, 1]: score = 1 - distance/2.
On any exception: raise RetrievalError (caller handles fallback).
"""

import logging

import chromadb
from openai import AsyncOpenAI

from app.config import settings
from app.errors import RetrievalError
from app.models.retrieval import Hit

logger = logging.getLogger(__name__)

COLLECTION_NAME = "rag_stage1"

_openai_client = AsyncOpenAI(api_key=settings.openai_api_key)


def _get_collection() -> chromadb.Collection:
    """Return the rag_stage1 Chroma collection (same client setup as ingestion)."""
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


async def semantic_search(query: str, top_k: int = 10) -> list[Hit]:
    """Embed *query* and retrieve the top-k most similar chunks from Chroma.

    Embedding: OpenAI SDK directly.
    Retrieval: chromadb collection.query() with the pre-computed embedding vector.
    Score conversion: cosine distance in [0,2] → similarity in [0,1]: 1 - d/2.

    Raises RetrievalError on any exception; caller (retrieve.py) handles fallback.
    """
    logger.info("semantic_search: query=%r top_k=%d", query, top_k)

    try:
        # 1. Embed the query with OpenAI SDK directly
        embed_response = await _openai_client.embeddings.create(
            model=settings.embed_model,
            input=[query],
        )
        embedding: list[float] = embed_response.data[0].embedding
        logger.info("semantic_search: embedded query dims=%d", len(embedding))

        # 2. Query Chroma with the pre-computed embedding
        collection = _get_collection()
        results = collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        # results shape: each key maps to a list-of-lists (one list per query)
        ids: list[str] = results["ids"][0]
        documents: list[str] = results["documents"][0]
        metadatas: list[dict] = results["metadatas"][0]
        distances: list[float] = results["distances"][0]

        hits: list[Hit] = []
        for chunk_id, text, meta, distance in zip(ids, documents, metadatas, distances):
            # Cosine distance in [0, 2] → similarity in [0, 1]
            score = max(0.0, 1.0 - distance / 2.0)
            hits.append(
                Hit(
                    chunk_id=chunk_id,
                    document_id=meta["document_id"],
                    filename=meta["filename"],
                    chunk_index=int(meta["chunk_index"]),
                    text=text,
                    source_page=meta.get("source_page"),
                    score=score,
                    source="semantic",
                )
            )

        logger.info(
            "semantic_search: done num_hits=%d top_score=%.4f",
            len(hits),
            hits[0].score if hits else 0.0,
        )
        return hits

    except Exception as exc:
        logger.error("semantic_search: failed: %s", exc, exc_info=True)
        raise RetrievalError("semantic search failed") from exc
