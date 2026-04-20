"""Generation step — Phase 1.

Loads prompts/generation.txt at module import; fails loudly if missing.
Uses OpenAI SDK directly: gpt-4o-mini, temperature=0.2, max_tokens=1024.
On empty context: yields CANNED_MESSAGE, no LLM call.
On OpenAI 5xx: one retry after 2s. On second failure or mid-stream error:
    yields '\n\n[Generation interrupted]'.
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import AsyncIterator

import openai
from openai import AsyncOpenAI

from app.config import settings
from app.models.retrieval import Hit
from app.observability.langsmith import generation_span

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANNED_MESSAGE = "I cannot answer this question from your uploaded documents."

# ---------------------------------------------------------------------------
# Load prompt at import time — hard fail if missing
# ---------------------------------------------------------------------------

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "generation.txt"

if not _PROMPT_PATH.exists():
    raise FileNotFoundError(
        f"generate.py: prompt file not found at {_PROMPT_PATH}. "
        "Create prompts/generation.txt before starting the server."
    )

GENERATION_TEMPLATE: str = _PROMPT_PATH.read_text(encoding="utf-8")
logger.info("generate: loaded prompt from %s (%d chars)", _PROMPT_PATH, len(GENERATION_TEMPLATE))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_client = AsyncOpenAI(api_key=settings.openai_api_key)


def _build_context(hits: list[Hit]) -> str:
    """Build numbered [N] context block from semantic hits.

    Skips hits with empty .text. Returns "" if all are empty (triggers canned msg).
    """
    blocks: list[str] = []
    idx = 1
    for hit in hits:
        if not hit.text:
            continue
        header = f"[{idx}] filename={hit.filename}"
        if hit.source_page is not None:
            header += f" · p.{hit.source_page}"
        blocks.append(f"{header}\n{hit.text}")
        idx += 1
    return "\n\n".join(blocks)


def _format_history(messages: list) -> str:
    """Render chat history as 'User: …\\nAssistant: …'.

    Skips assistant turns whose content starts with CANNED_MESSAGE.
    """
    parts: list[str] = []
    for msg in messages:
        role = str(msg.role)
        if role in ("assistant", "MessageRole.assistant") and msg.content.startswith(CANNED_MESSAGE):
            continue
        label = "User" if role in ("user", "MessageRole.user") else "Assistant"
        parts.append(f"{label}: {msg.content}")
    return "\n".join(parts)


async def _create_stream(prompt_text: str):
    return await _client.chat.completions.create(
        model=settings.gen_model,
        messages=[{"role": "user", "content": prompt_text}],
        stream=True,
        stream_options={"include_usage": True},
        temperature=0.2,
        max_tokens=1024,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def generate(
    question: str,
    semantic_hits: list[Hit],
    chat_history: list,
) -> AsyncIterator[str]:
    """Yield answer tokens for *question* grounded in *semantic_hits*.

    If semantic_hits is empty or all have empty text: yields CANNED_MESSAGE, no LLM call.
    """
    context = _build_context(semantic_hits)

    if not context:
        logger.warning(
            "generate: empty context (hits=%d), returning canned message", len(semantic_hits)
        )
        async with generation_span(
            model=settings.gen_model,
            num_context_chunks=0,
            history_turns=len(chat_history),
            skipped=True,
            reason="no_hits",
        ):
            pass
        yield CANNED_MESSAGE
        return

    history_str = _format_history(chat_history)
    prompt_text = GENERATION_TEMPLATE.format(
        context=context,
        history=history_str,
        question=question,
    )
    logger.info(
        "generate: prompt_chars=%d num_hits=%d history_msgs=%d",
        len(prompt_text),
        len(semantic_hits),
        len(chat_history),
    )

    async with generation_span(
        model=settings.gen_model,
        num_context_chunks=len(semantic_hits),
        history_turns=len(chat_history),
    ) as attrs:
        full_answer = ""

        # --- Create stream (with one 5xx retry) ---
        stream = None
        try:
            stream = await _create_stream(prompt_text)
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                logger.warning(
                    "generate: openai %d, retrying after 2s", exc.status_code
                )
                await asyncio.sleep(2)
                try:
                    stream = await _create_stream(prompt_text)
                except Exception as exc2:
                    logger.error("generate: retry failed: %s", exc2, exc_info=True)
                    yield "\n\n[Generation interrupted]"
                    return
            else:
                logger.error("generate: openai error: %s", exc, exc_info=True)
                yield "\n\n[Generation interrupted]"
                return
        except Exception as exc:
            logger.error("generate: openai call failed: %s", exc, exc_info=True)
            yield "\n\n[Generation interrupted]"
            return

        # --- Stream tokens ---
        try:
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        full_answer += delta
                        yield delta
                if chunk.usage:
                    attrs["prompt_tokens"] = chunk.usage.prompt_tokens
                    attrs["completion_tokens"] = chunk.usage.completion_tokens
        except Exception as exc:
            logger.error("generate: mid-stream exception: %s", exc, exc_info=True)
            full_answer += "\n\n[Generation interrupted]"
            yield "\n\n[Generation interrupted]"

        # --- Post-stream: citation analysis ---
        citation_nums = re.findall(r'\[(\d+)\]', full_answer)
        attrs["citations_present"] = len(citation_nums) > 0
        attrs["citation_out_of_range"] = any(
            int(n) > len(semantic_hits) for n in citation_nums
        )
        logger.info(
            "generate: done answer_chars=%d citations=%s out_of_range=%s",
            len(full_answer),
            attrs["citations_present"],
            attrs["citation_out_of_range"],
        )
