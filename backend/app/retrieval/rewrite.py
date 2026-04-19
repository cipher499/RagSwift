"""Query rewriter — Phase 1.

Loads prompts/rewrite.txt once at module import and fails loudly if missing.
Uses OpenAI SDK directly: gpt-4o-mini, temperature=0.0, max_tokens=200.
On any exception returns the original query with rewrite_fallback=True.
"""

import logging
from pathlib import Path

from openai import AsyncOpenAI

from app.config import settings
from app.models.retrieval import RewriteResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load prompt at import time — hard fail if file is missing
# ---------------------------------------------------------------------------

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "rewrite.txt"

if not _PROMPT_PATH.exists():
    raise FileNotFoundError(
        f"rewrite.py: prompt file not found at {_PROMPT_PATH}. "
        "Create prompts/rewrite.txt before starting the server."
    )

_SYSTEM_PROMPT: str = _PROMPT_PATH.read_text(encoding="utf-8").strip()
logger.info("rewrite: loaded prompt from %s (%d chars)", _PROMPT_PATH, len(_SYSTEM_PROMPT))

# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

_client = AsyncOpenAI(api_key=settings.openai_api_key)


async def rewrite(question: str) -> RewriteResult:
    """Rewrite *question* into a better semantic search query.

    On any exception: logs WARNING, returns original query, sets is_noop=True.
    The caller is responsible for propagating rewrite_fallback into the trace flags.
    """
    logger.info("rewrite: input=%r", question)

    try:
        response = await _client.chat.completions.create(
            model=settings.gen_model,
            temperature=0.0,
            max_tokens=200,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
        )
        rewritten = (response.choices[0].message.content or "").strip()

        if not rewritten:
            logger.warning("rewrite: empty response from model, using original query")
            return RewriteResult(
                original_query=question,
                rewritten_query=question,
                is_noop=True,
            )

        is_noop = rewritten.strip().lower() == question.strip().lower()
        logger.info("rewrite: output=%r is_noop=%s", rewritten, is_noop)
        return RewriteResult(
            original_query=question,
            rewritten_query=rewritten,
            is_noop=is_noop,
        )

    except Exception as exc:
        logger.warning("rewrite: exception, falling back to original query: %s", exc, exc_info=True)
        return RewriteResult(
            original_query=question,
            rewritten_query=question,
            is_noop=True,
            rewrite_fallback=True,
        )
