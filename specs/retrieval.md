# specs/retrieval.md

> Retrieval pipeline spec. `CLAUDE.md` governs phase discipline, failure philosophy, and model constraints.

## 1. Pipelines

```
P1: query → rewrite → semantic                          → generate
P2: query → rewrite → BM25 ∥ semantic → fusion          → generate
P3: query → rewrite → BM25 ∥ semantic → fusion → rerank → generate
P4: route → rewrite → BM25 ∥ semantic → fusion → rerank → generate
```

`∥` = `asyncio.gather`. Order fixed per phase. P2 implements BM25 + fusion together — no standalone BM25-only phase.

## 2. Constants

All values from `backend/app/retrieval/constants.py`. Never hardcode. Reference: `SEMANTIC_TOP_K`, `BM25_TOP_K`, `RRF_K`, `FUSED_TOP_K`, `RERANK_TOP_K`.

## 3. Step Contracts

### 3.1 Rewrite

```python
async def rewrite(question: str) -> RewriteResult: ...

class RewriteResult(BaseModel):
    original_query: str
    rewritten_query: str
    is_noop: bool   # True if rewritten == original (stripped, lowercased)
```

- OpenAI `chat.completions.create`, `model="gpt-4o-mini"`, `temperature=0.0`, `max_tokens=200`.
- Load `prompts/rewrite.txt` at module import; fail loudly if missing.
- On exception: return original query, set `rewrite_fallback=True`, log WARNING.

### 3.2 Semantic Search

```python
async def semantic_search(query: str, top_k: int = SEMANTIC_TOP_K) -> list[Hit]: ...
```

- Embed with OpenAI `text-embedding-3-small` via SDK.
- Query Chroma `rag_stage1`; convert distance: `score = 1 - (distance / 2)`.
- `score` = cosine similarity. `source="semantic"`.
- On exception: raise `RetrievalError("semantic search failed")`.

### 3.3 BM25 Search (P2+)

```python
def bm25_search(query: str, top_k: int = BM25_TOP_K) -> list[Hit]: ...
```

- In-memory `BM25Okapi` singleton. Tokenize: `re.findall(r"\b\w+\b", text.lower())` — applied to both corpus and query.
- `score` = raw BM25 score. `source="bm25"`.
- `rebuild(nodes: list[TextNode])` called on startup and after every ingestion.
- Empty index returns `[]`, does not raise.
- On exception: raise `RetrievalError("bm25 search failed")`.

### 3.4 Fusion — RRF (P2+)

```python
def fuse(bm25_hits: list[Hit], semantic_hits: list[Hit], k: int = RRF_K, top_k: int = FUSED_TOP_K) -> list[Hit]: ...
```

- Accumulate RRF contributions: `score(chunk) += 1 / (k + rank + 1)` for each list, rank 0-indexed.
- Deduplicate by `chunk_id`. Populate `bm25_rank`, `semantic_rank` (0-indexed; `None` if absent).
- Output: top-k by fused score, `source="fused"`, `score=rrf_score`, `rrf_score=rrf_score`.
- If only one list is non-empty, run fusion over that single list.

### 3.5 Rerank — Cohere (P3+)

```python
async def rerank(query: str, candidates: list[Hit], top_k: int = RERANK_TOP_K) -> list[Hit]: ...
```

- `cohere.AsyncClient(api_key=settings.cohere_api_key)`.
- Call: `co.rerank(query=query, documents=[f"{h.filename}\n\n{h.text}" for h in candidates], model=settings.cohere_rerank_model, top_n=top_k)`.
- Map by index: preserve all existing fields including `score` (RRF value retained). Set `rerank_score=result.relevance_score`, `source="reranked"`. Sort by `rerank_score` descending.
- On exception: raise `RerankerError("cohere rerank failed")`.

### 3.6 Retrieve — Orchestrator

`final_hits` is what `generate()` always receives.

**P1:**
```python
async def retrieve(rewritten_query: str) -> RetrievalResult:
    try:
        hits = await semantic_search(rewritten_query)
        return RetrievalResult(semantic_hits=hits, final_hits=hits, flags={})
    except Exception as e:
        logger.warning("semantic_fallback", exc_info=e)
        return RetrievalResult(semantic_hits=[], final_hits=[], flags={"semantic_fallback": True})
```

**P2:** Run `asyncio.gather(asyncio.to_thread(bm25_search, q), semantic_search(q), return_exceptions=True)`. Apply fallback hierarchy (§5). Call `fuse(bm25_hits, semantic_hits)`. Set `final_hits = fused_hits`.

**P3:** Same as P2, then `await rerank(rewritten_query, fused_hits)`. On `RerankerError`: `rerank_fallback=True`, `final_hits = fused_hits[:RERANK_TOP_K]`. On success: `final_hits = reranked_hits`.

## 4. Schemas

### Hit

```python
class Hit(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    chunk_index: int
    text: str
    source_page: int | None
    score: float        # cosine (P1), raw BM25 (bm25 hits), RRF (fused/reranked hits)
    source: Literal["semantic", "bm25", "fused", "reranked"]
    rrf_score:    float | None = None   # P2+
    bm25_rank:    int | None   = None   # P2+
    semantic_rank: int | None  = None   # P2+
    rerank_score: float | None = None   # P3+; Cohere relevance, independent of score
```

Add phase-specific fields only when that phase is implemented.

### RetrievalResult

```python
class RetrievalResult(BaseModel):
    semantic_hits:  list[Hit] = []
    bm25_hits:      list[Hit] = []   # P2+
    fused_hits:     list[Hit] = []   # P2+
    reranked_hits:  list[Hit] = []   # P3+
    final_hits:     list[Hit]
    flags:          dict[str, bool] = {}
    # keys: semantic_fallback, bm25_fallback, rewrite_fallback, rerank_fallback
```

## 5. Fallback Hierarchy

**P1:** semantic fails → `semantic_fallback=True`, `final_hits=[]`.

**P2+:**
```
semantic ok  ∧ bm25 ok   → fuse normally
semantic ok  ∧ bm25 fail → bm25_fallback=True;     fuse over semantic_hits only
semantic fail ∧ bm25 ok  → semantic_fallback=True; fuse over bm25_hits only
both fail                → both flags=True;        final_hits=[]
```

**P3:** reranker fails → `rerank_fallback=True`, `final_hits = fused_hits[:RERANK_TOP_K]`.

All fallbacks: log WARNING with exception, set flag in `RetrievalResult.flags`.

## 6. Trace Fields

| Phase | Trace fields added |
|---|---|
| P1 | `semantic_hits_json` |
| P2 | `bm25_hits_json`, `fused_hits_json` |
| P3 | `reranked_hits_json` |

Stored as JSON strings. Deserialised on `GET /api/chats/{id}/traces/{trace_id}`.

## 7. SSE `trace_partial` Events

| Phase | Events emitted (in order) |
|---|---|
| P1 | `{rewritten_query}`, `{semantic_hits}` |
| P2 | `{rewritten_query}`, `{bm25_hits, semantic_hits}`, `{fused_hits}` |
| P3 | same as P2 + `{reranked_hits}` |

Frontend disambiguates by key presence in payload.

## 8. LangSmith Spans

```
chat_turn
├── rewrite       attrs: is_noop, rewrite_fallback?
├── retrieve
│   ├── bm25      attrs: num_hits, latency_ms, bm25_fallback?        [P2+]
│   ├── semantic  attrs: num_hits, latency_ms, semantic_fallback?
│   ├── fusion    attrs: num_fused                                    [P2+]
│   └── rerank    attrs: num_scored, rerank_fallback?                 [P3+]
└── generate
```

Skipped steps open and close with `skipped=True`.

## 9. Startup

1. Confirm `gpt-4o-mini` accessible; else STOP.
2. `chromadb.PersistentClient.heartbeat()`.
3. P2+: load all chunks from `rag_stage1`, call `bm25_retriever.rebuild(nodes)`.
4. P3+: instantiate `cohere.AsyncClient` to validate key. No API call on startup.
5. Load all `prompts/*.txt`.

## 10. Success Criteria

**P2:** `bm25_hits` and `semantic_hits` non-empty on a real query. Fused scores ~0.01–0.03 (RRF range). Chunk in both lists scores higher than one in only one list. Fallback flags set correctly when either retriever raises.

**P3:** `reranked_hits` length ≤ `RERANK_TOP_K`. `rerank_score` = Cohere float. `score` retains RRF value. `rerank_fallback` path returns `fused_hits[:RERANK_TOP_K]`.