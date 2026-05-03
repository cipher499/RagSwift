import asyncio
import logging

from openai import AsyncOpenAI
from llama_index.core.schema import TextNode

from app.config import settings
from app.errors import IngestionError

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100
_MAX_RETRIES = 3

async def embed_chunks(nodes: list[TextNode]) -> tuple[list[TextNode], list[list[float]]]:
    """Embed a list of TextNodes using the OpenAI embeddings API.

    Batches up to 100 nodes per call.  Retries up to 3 times on any error
    with exponential backoff (1 s, 2 s, 4 s).

    Raises IngestionError if all retries are exhausted.
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    nodes = [n for n in nodes if n.text and n.text.strip()]
    if not nodes:
      raise IngestionError("all chunks were empty after filtering", step="embed")
    batches = [nodes[i : i + _BATCH_SIZE] for i in range(0, len(nodes), _BATCH_SIZE)]

    logger.info(
        "embed_chunks: start num_nodes=%d num_batches=%d model=%s",
        len(nodes),
        len(batches),
        settings.embed_model,
    )

    all_embeddings: list[list[float]] = []

    for batch_idx, batch in enumerate(batches):
        texts = [node.text for node in batch if node.text and node.text.strip()]

        for attempt in range(_MAX_RETRIES):
            try:
                response = await client.embeddings.create(
                    model=settings.embed_model,
                    input=texts,
                )
                all_embeddings.extend(item.embedding for item in response.data)
                logger.info(
                    "embed_chunks: batch %d/%d ok attempt=%d",
                    batch_idx + 1,
                    len(batches),
                    attempt + 1,
                )
                break
            except Exception as exc:
                wait = 2**attempt  # 1 s, 2 s, 4 s
                if attempt < _MAX_RETRIES - 1:
                    logger.warning(
                        "embed_chunks: batch %d attempt %d failed, retrying in %ds: %s",
                        batch_idx + 1,
                        attempt + 1,
                        wait,
                        exc,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "embed_chunks: all retries exhausted for batch %d: %s",
                        batch_idx + 1,
                        exc,
                    )
                    raise IngestionError("embedding service unavailable", step="embed")

    logger.info("embed_chunks: done total=%d", len(all_embeddings))
    return nodes,all_embeddings
