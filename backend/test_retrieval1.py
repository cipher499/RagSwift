import asyncio
import sys

sys.path.insert(0, "backend")

from app.retrieval import retrieve

async def main():
    result = await retrieve("What does the book say about discipline?")
    print("Flags:", result.flags)
    print("Hits:", len(result.semantic_hits))

    for h in result.semantic_hits:
        print(f"[{h.score:.3f}] {h.filename} chunk={h.chunk_index}: {h.text[:100]!r}")

asyncio.run(main())