# specs/retrieval.md — Phase 1

> Retrieval pipeline. Reads `CLAUDE.md` §6 (Phase-aware pipeline), §7 (Model), §10 (Failure Philosophy).

## 1. Phase 1 Pipeline

```
query → rewrite → semantic → generate
```

Strict order. No BM25, no fusion, no rerank, no router. Those are Phases 2–5 — do NOT implement them now.

## 2. Step Contracts

### 2.1 Rewrite

```python
async def rewrite(question: str) -> RewriteResult: ...

class RewriteResult(BaseModel):
    original_query: str
    rewritten_query: str
    is_noop: bool                    # True if rewritten == original (stripped, lowercased)
```

- Call OpenAI `chat.completions.create` directly with `model="gpt-4o-mini"`, `temperature=0.0`, `max_tokens=200`.
- Prompt: load `prompts/rewrite.txt` once at startup.
- Single rewrite only. No multi-query expansion. No HyDE.
- On exception: return `RewriteResult(original_query=question, rewritten_query=question, is_noop=True)` and set trace flag `rewrite_fallback=True`. Log WARNING.

### 2.2 Semantic Search

```python
async def semantic_search(query: str, top_k: int = 10) -> list[Hit]: ...
```

- Embed `query` with OpenAI `text-embedding-3-small` (use SDK directly).
- Query Chroma collection `rag_stage1` with `collection.query(query_embeddings=[embedding], n_results=top_k)`.
- Chroma returns distances in `[0, 2]` for cosine. Convert to similarity: `score = 1 - (distance / 2)`.
- Map each Chroma result row to a `Hit` object (§3).
- On exception: raise `RetrievalError("semantic search failed")`. Caller (`retrieve()`) handles fallback per `CLAUDE.md` §10.

### 2.3 Retrieve (Phase 1 orchestrator)

```python
async def retrieve(query: str) -> RetrievalResult:
    try:
        hits = await semantic_search(query, top_k=10)
        return RetrievalResult(semantic_hits=hits, flags={})
    except Exception as e:
        logger.warning("semantic_fallback", exc_info=e)
        return RetrievalResult(semantic_hits=[], flags={"semantic_fallback": True})

class RetrievalResult(BaseModel):
    semantic_hits: list[Hit]          # may be empty
    flags: dict[str, bool]            # semantic_fallback, rewrite_fallback
```

- In Phase 1, `semantic_hits` IS the final context list passed to generation.
- No truncation below 10 in Phase 1 — pass all 10 to generation. (Phase 4 adds rerank-to-3.)
- If `semantic_hits` is empty: generation emits the canned "cannot answer" message (see `specs/generation.md` §2).

## 3. Hit Schema

```python
class Hit(BaseModel):
    chunk_id: str                    # "doc_abc:0007"
    document_id: str
    filename: str
    chunk_index: int
    text: str                        # full chunk text
    source_page: int | None
    score: float                     # cosine similarity in [0, 1]
    source: Literal["semantic"]      # Phase 1: always "semantic"
```

Phase 2+ extends this schema with `source ∈ {bm25, fused, reranked}` and additional fields — do NOT add those fields yet.

## 4. Failure Cascade (Phase 1)

Per `CLAUDE.md` §10:

- `semantic` fails → return empty hits with `semantic_fallback=True` → generation emits `"I cannot answer this question from your uploaded documents"`.
- `rewrite` fails → use original query with `rewrite_fallback=True` → continue to semantic.

Every fallback:
- logs at WARNING level with the exception
- sets its flag in `RetrievalResult.flags`
- is surfaced in the trace

No silent fallback. No generation from LLM general knowledge.

## 5. LangSmith Spans

```
chat_turn (root)
├── rewrite         (attributes: is_noop, rewrite_fallback?)
├── retrieve
│   └── semantic    (attributes: num_hits, latency_ms, semantic_fallback?)
└── generate        (see specs/generation.md)
```

Use `@traceable` on each function. Ensure `LANGSMITH_TRACING=true` in env or spans silently no-op.

## 6. Startup Requirements

On backend startup:

1. Verify OpenAI API: call `client.models.list()`. If `gpt-4o-mini` or `text-embedding-3-small` is not in the list, STOP startup with a clear error (per `CLAUDE.md` §7).
2. Verify Chroma: `chromadb.PersistentClient(path=...).heartbeat()`.
3. Create `rag_stage1` collection if missing.
4. Load prompt files from `prompts/`.

## 7. Success Criteria (Phase 1)

- End-to-end (rewrite + semantic + generate) completes in under 5 seconds for a 10-document collection.
- Every call produces a trace row with `semantic_hits` populated (possibly empty) and correct `flags`.
- Fallbacks are always logged AND flagged AND visible in the trace — never silent.
- No BM25, fusion, rerank, or router code exists in the codebase at end of Phase 1.

## 8. What Phase 1 Does NOT Include

- No BM25 (Phase 2).
- No RRF fusion (Phase 3).
- No cross-encoder reranking (Phase 4).
- No router (Phase 5).
- No `direct_answer` branch. Every query goes through rewrite + semantic.
- No `refuse` branch.

If zero hits come back, answer with the canned "cannot answer" message. Nothing else.