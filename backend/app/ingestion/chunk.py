import logging

import tiktoken
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document as LIDocument, TextNode

from app.errors import IngestionError

logger = logging.getLogger(__name__)


def chunk_document(
    documents: list[LIDocument],
    document_id: str,
    filename: str,
) -> list[TextNode]:
    """Chunk LlamaIndex Documents into TextNodes with deterministic IDs.

    Raises IngestionError if no chunks are produced.
    """
    logger.info(
        "chunk_document: start document_id=%s num_docs=%d",
        document_id,
        len(documents),
    )

    # Use cl100k_base via encoding_for_model as specified in ingestion.md §3.2
    enc = tiktoken.encoding_for_model("gpt-4o-mini")
    splitter = SentenceSplitter(
        chunk_size=512,
        chunk_overlap=64,
        tokenizer=enc.encode,
    )

    nodes: list[TextNode] = splitter.get_nodes_from_documents(documents)

    if not nodes:
        raise IngestionError("no chunks produced", step="chunk")

    for index, node in enumerate(nodes):
        # Deterministic ID: "<document_id>:<zero-padded-index>"
        node.id_ = f"{document_id}:{index:04d}"

        # Extract source page from LlamaIndex metadata (PDFs carry page_label)
        raw_page = node.metadata.get("page_label") or node.metadata.get("page")
        source_page: int | None = None
        if raw_page is not None:
            try:
                source_page = int(raw_page)
            except (ValueError, TypeError):
                source_page = None

        node.metadata = {
            "document_id": document_id,
            "filename": filename,
            "chunk_index": index,
            "source_page": source_page,
        }

    logger.info("chunk_document: done num_chunks=%d", len(nodes))
    return nodes
