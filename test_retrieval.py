"""Manual integration test for the Phase 1 retriever.

Runs against the real Chroma collection (data/chroma) and real OpenAI API.
Requires OPENAI_API_KEY in .env and at least one indexed document.

Run with:
    uv run pytest test_retrieval.py -s -v
"""

import asyncio
import json
import pytest


@pytest.mark.asyncio
async def test_retrieve_prints_result():
    from app.retrieval import retrieve

    query = "What is the main theme of the book?"
    print(f"\n{'='*60}")
    print(f"Query: {query!r}")
    print('='*60)

    result = await retrieve(query)

    print(f"\nFlags: {result.flags}")
    print(f"Hits : {len(result.semantic_hits)}")
    print()

    for i, hit in enumerate(result.semantic_hits):
        print(f"  [{i+1}] score={hit.score:.4f}  chunk_id={hit.chunk_id}")
        print(f"       file={hit.filename}  page={hit.source_page}  idx={hit.chunk_index}")
        print(f"       text={hit.text[:120]!r}")
        print()

    # Structural assertions — not content assertions
    assert isinstance(result.semantic_hits, list), "semantic_hits must be a list"
    assert "semantic_fallback" not in result.flags or result.flags["semantic_fallback"] is True

    if result.semantic_hits:
        hit = result.semantic_hits[0]
        assert 0.0 <= hit.score <= 1.0, f"score out of [0,1]: {hit.score}"
        assert hit.source == "semantic"
        assert hit.chunk_id != ""
        assert hit.document_id != ""
        assert hit.text != ""

    print("PASS")
