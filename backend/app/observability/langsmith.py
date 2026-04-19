"""LangSmith tracing helpers.

Tracing is opt-in: set LANGSMITH_TRACING=true in .env.
All functions are no-ops when tracing is disabled.
langsmith is imported inside function bodies to avoid hard import failure.
"""

import logging
from contextlib import asynccontextmanager

from app.config import settings

logger = logging.getLogger(__name__)


def tracing_enabled() -> bool:
    return settings.langsmith_tracing.lower() == "true"


@asynccontextmanager
async def generation_span(
    *,
    model: str,
    num_context_chunks: int,
    history_turns: int,
    skipped: bool = False,
    reason: str | None = None,
):
    """Open a LangSmith 'generate' span.

    Yields a mutable attrs dict. Caller populates it with:
        prompt_tokens, completion_tokens, citations_present, citation_out_of_range.

    No-op when tracing is disabled or langsmith is unavailable.
    """
    attrs: dict = {}

    if not tracing_enabled():
        yield attrs
        return

    try:
        import uuid as _uuid
        from datetime import datetime, timezone

        import langsmith as ls

        client = ls.Client(api_key=settings.langsmith_api_key)
        run_id = str(_uuid.uuid4())
        start = datetime.now(timezone.utc)

        inputs: dict = {
            "model": model,
            "num_context_chunks": num_context_chunks,
            "history_turns": history_turns,
        }
        if skipped:
            inputs["skipped"] = True
            inputs["reason"] = reason

        try:
            client.create_run(
                id=run_id,
                name="generate",
                run_type="llm",
                inputs=inputs,
                start_time=start,
                project_name=settings.langsmith_project,
            )
        except Exception as exc:
            logger.warning("langsmith: create_run failed (%s), continuing without trace", exc)
            yield attrs
            return

        try:
            yield attrs
        finally:
            try:
                from datetime import datetime, timezone as _tz
                client.update_run(
                    run_id=run_id,
                    outputs=attrs,
                    end_time=datetime.now(_tz.utc),
                )
            except Exception as exc:
                logger.warning("langsmith: update_run failed: %s", exc)

    except Exception as exc:
        logger.warning("langsmith: span setup failed (%s), continuing without trace", exc)
        yield attrs
