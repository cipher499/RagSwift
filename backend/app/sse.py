"""Shared helpers for building SSE event dicts consumed by EventSourceResponse."""

import json
from typing import Any


def _event(event: str, data: dict[str, Any]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data)}


def step_event(step: str, state: str, progress_pct: int, message: str | None = None) -> dict:
    return _event("step", {
        "step": step,
        "state": state,
        "progress_pct": progress_pct,
        "message": message,
    })


def done_event(document_id: str, num_chunks: int, num_pages: int | None) -> dict:
    return _event("done", {
        "document_id": document_id,
        "num_chunks": num_chunks,
        "num_pages": num_pages,
    })


def error_event(step: str, error: str, detail: str) -> dict:
    return _event("error", {
        "step": step,
        "error": error,
        "detail": detail,
    })
