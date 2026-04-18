import logging
from pathlib import Path

from llama_index.core import SimpleDirectoryReader
from llama_index.core.schema import Document as LIDocument

from app.errors import IngestionError

logger = logging.getLogger(__name__)


def parse_document(file_path: Path) -> list[LIDocument]:
    """Parse a file into LlamaIndex Documents using SimpleDirectoryReader.

    Raises IngestionError if no text could be extracted.
    """
    logger.info("parse_document: start file=%s", file_path)

    documents: list[LIDocument] = SimpleDirectoryReader(
        input_files=[str(file_path)]
    ).load_data()

    if not documents or all(not (d.text or "").strip() for d in documents):
        raise IngestionError("no extractable text", step="parse")

    logger.info(
        "parse_document: done num_documents=%d total_chars=%d",
        len(documents),
        sum(len(d.text or "") for d in documents),
    )
    return documents
