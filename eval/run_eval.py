"""RAG eval script — three modes: interactive (default), --batch, --browse.

Run from project root:
    python eval/run_eval.py
    python eval/run_eval.py --batch
    python eval/run_eval.py --browse "search term"
"""

import sys
import json
import argparse
import asyncio
import logging
from datetime import datetime
from pathlib import Path

# --- sys.path: add backend/ so `from app.xxx` imports work ---
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from openai import AsyncOpenAI  # noqa: E402
import chromadb  # noqa: E402

from app.retrieval.retrieve import retrieve  # noqa: E402
from app.config import settings  # noqa: E402
from app.models.retrieval import RetrievalResult  # noqa: E402

# Suppress INFO-level noise from the retrieval pipeline during eval runs.
logging.basicConfig(level=logging.WARNING)

TESTSET_PATH = ROOT / "eval" / "testset.json"
RESULTS_DIR = ROOT / "eval" / "results"

# Update this manually when you move to the next pipeline phase.
PIPELINE_VERSION = "phase1_semantic"
_openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_testset() -> list[dict]:
    if not TESTSET_PATH.exists():
        return []
    with open(TESTSET_PATH) as f:
        return json.load(f)

def save_testset(testset: list[dict]) -> None:
    with open(TESTSET_PATH, "w") as f:
        json.dump(testset, f, indent=2)

def compute_recall(relevant: list[str], retrieved: list[str]) -> float:
    if not relevant:
        return 0.0
    return sum(1 for c in relevant if c in retrieved) / len(relevant)


def compute_mrr(relevant: list[str], retrieved: list[str]) -> float:
    relevant_set = set(relevant)
    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant_set:
            return 1.0 / rank
    return 0.0


def get_chroma_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    return client.get_or_create_collection(
        name="rag_stage1",
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def interactive_mode() -> None:
    print("=== RAG Eval — Interactive Mode ===")
    print(f"Pipeline: {PIPELINE_VERSION}  |  ChromaDB: {settings.chroma_persist_dir}")
    testset = load_testset()

    while True:
        print()
        try:
            query = input("Enter query (or 'quit'): ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if query.lower() in ("quit", "q", ""):
            break

        result: RetrievalResult = asyncio.run(retrieve(query))
        hits = result.semantic_hits

        if not hits:
            print("No results returned.")
            if result.flags:
                print(f"Flags: {result.flags}")
            continue

        hits = hits[:7]
        print(f"\nTop {len(hits)} results:")
        for i, hit in enumerate(hits):
            print(f"  [{i}] chunk_id={hit.chunk_id}  score={hit.score:.4f}  file={hit.filename}")
            print(f"       {hit.text!r}")
            print()

        if result.flags:
            print(f"Pipeline flags: {result.flags}")

        try:
            relevant_input = input(
                "Which chunks are relevant? (indices like 0,2,3 or 'skip'): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            break

        if relevant_input.lower() == "skip":
            continue

        try:
            indices = [int(x.strip()) for x in relevant_input.split(",") if x.strip()]
        except ValueError:
            print("Invalid input, skipping.")
            continue

        valid_indices = [i for i in indices if 0 <= i < len(hits)]
        relevant_ids = [hits[i].chunk_id for i in valid_indices]
        retrieved_ids = [h.chunk_id for h in hits]

        recall = compute_recall(relevant_ids, retrieved_ids)
        mrr = compute_mrr(relevant_ids, retrieved_ids)

        print(f"\nRecall@{len(hits)}: {recall:.4f}")
        print(f"MRR:         {mrr:.4f}")

        try:
            save_input = input("Save to testset? (y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if save_input == "y":
            entry = {
                "query": query,
                "relevant_chunks": relevant_ids,
                "retrieved_chunks_snapshot": [
                    {
                        "chunk_id": h.chunk_id,
                        "score": h.score,
                        "text_preview": h.text[:500],
                    }
                    for h in hits
                ],
                "recall_at_k": recall,
                "mrr": mrr,
                "k": len(hits),
                "timestamp": datetime.utcnow().isoformat(),
                "pipeline_version": PIPELINE_VERSION,
            }
            testset.append(entry)
            save_testset(testset)
            print(f"Saved. Testset now has {len(testset)} entr{'y' if len(testset) == 1 else 'ies'}.")


# ---------------------------------------------------------------------------
# Batch mode
# ---------------------------------------------------------------------------

def batch_mode() -> None:
    testset = load_testset()
    if not testset:
        print("Testset is empty. Run interactive mode to add queries first.")
        return

    print(f"=== RAG Eval — Batch Mode ({len(testset)} queries) ===")
    print(f"Pipeline: {PIPELINE_VERSION}  |  ChromaDB: {settings.chroma_persist_dir}\n")

    col_q = 52
    header = f"{'Query':<{col_q}} {'Recall@k':>8} {'MRR':>6} {'Changed?':>10}"
    print(header)
    print("-" * len(header))

    all_recall: list[float] = []
    all_mrr: list[float] = []
    batch_results: list[dict] = []

    for entry in testset:
        query = entry["query"]
        relevant = entry["relevant_chunks"]
        saved_recall = entry["recall_at_k"]
        saved_mrr = entry["mrr"]

        result: RetrievalResult = asyncio.run(retrieve(query))
        hits = result.semantic_hits
        retrieved_ids = [h.chunk_id for h in hits]

        recall = compute_recall(relevant, retrieved_ids)
        mrr = compute_mrr(relevant, retrieved_ids)

        changed = (abs(recall - saved_recall) > 1e-4) or (abs(mrr - saved_mrr) > 1e-4)
        changed_label = "YES" if changed else "no"

        all_recall.append(recall)
        all_mrr.append(mrr)

        q_display = (query[:col_q - 2] + "..") if len(query) > col_q else query
        print(f"{q_display:<{col_q}} {recall:>8.4f} {mrr:>6.4f} {changed_label:>10}")

        batch_results.append({
            "query": query,
            "relevant_chunks": relevant,
            "retrieved_chunk_ids": retrieved_ids,
            "recall_at_k": recall,
            "mrr": mrr,
            "k": len(hits),
            "saved_recall_at_k": saved_recall,
            "saved_mrr": saved_mrr,
            "changed": changed,
            "pipeline_version": PIPELINE_VERSION,
            "flags": result.flags,
        })

    avg_recall = sum(all_recall) / len(all_recall)
    avg_mrr = sum(all_mrr) / len(all_mrr)
    print("-" * len(header))
    print(f"{'AVERAGES':<{col_q}} {avg_recall:>8.4f} {avg_mrr:>6.4f}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{ts}.json"
    with open(out_path, "w") as f:
        json.dump(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "pipeline_version": PIPELINE_VERSION,
                "avg_recall_at_k": avg_recall,
                "avg_mrr": avg_mrr,
                "results": batch_results,
            },
            f,
            indent=2,
        )
    print(f"\nResults saved to {out_path.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Browse mode
# ---------------------------------------------------------------------------

async def _browse_embed_and_query(search_term: str) -> dict:
    embed_response = await _openai_client.embeddings.create(
        model=settings.embed_model,
        input=[search_term],
    )
    embedding = embed_response.data[0].embedding
    collection = get_chroma_collection()
    return collection.query(
        query_embeddings=[embedding],
        n_results=7,
        include=["documents", "metadatas", "distances"],
    )


def browse_mode(search_term: str) -> None:
    print(f"=== RAG Eval — Browse: {search_term!r} ===")
    print(f"ChromaDB: {settings.chroma_persist_dir}\n")

    results = asyncio.run(_browse_embed_and_query(search_term))

    ids = results["ids"][0]
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results["distances"][0]

    if not ids:
        print("No chunks found.")
        return

    for chunk_id, text, meta, dist in zip(ids, docs, metas, distances):
        score = max(0.0, 1.0 - dist / 2.0)
        print(f"chunk_id : {chunk_id}")
        print(f"score    : {score:.4f}")
        print(f"metadata : {meta}")
        print(f"text     : {text[:500]!r}")
        print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="RAG retrieval eval")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--batch", action="store_true", help="Batch re-run all testset queries")
    group.add_argument("--browse", metavar="TERM", help="Browse ChromaDB for a search term")
    args = parser.parse_args()

    if args.batch:
        batch_mode()
    elif args.browse:
        browse_mode(args.browse)
    else:
        interactive_mode()


if __name__ == "__main__":
    main()
