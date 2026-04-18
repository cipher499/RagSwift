import logging

import chromadb
from llama_index.core.schema import TextNode

from app.config import settings
from app.errors import IngestionError

logger = logging.getLogger(__name__)

COLLECTION_NAME = "rag_stage1"


async def index_chunks(nodes: list[TextNode], embeddings: list[list[float]]) -> None:
    """Upsert chunks and their embeddings into ChromaDB.

    Uses PersistentClient directly — no LlamaIndex wrapper.
    Collection uses cosine distance so retrieval scores map to [0, 1].

    Raises IngestionError on any ChromaDB exception.
    """
    logger.info("index_chunks: start num_nodes=%d collection=%s", len(nodes), COLLECTION_NAME)

    try:
        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        collection.upsert(
            ids=[node.id_ for node in nodes],
            embeddings=embeddings,
            documents=[node.text for node in nodes],
            metadatas=[node.metadata for node in nodes],
        )

        logger.info(
            "index_chunks: upserted %d chunks to collection=%s",
            len(nodes),
            COLLECTION_NAME,
        )
    except Exception as exc:
        logger.error("index_chunks: failed: %s", exc)
        raise IngestionError(f"chroma upsert failed: {exc}", step="index")
