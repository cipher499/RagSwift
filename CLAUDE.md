# CLAUDE.md — RAG MVP Stage I

> Single source of truth. Specs in `specs/`. On any conflict, `CLAUDE.md` wins.

## 1. What You Are Building

A single-user, no-auth RAG app. User uploads documents, watches ingestion, asks questions, gets grounded answers with visible retrieval internals, resumes chats.

**Capability:** query rewriting + semantic retrieval (baseline), with BM25, fusion, and reranking added sequentially in later phases for experimentation.

## 2. Required Reading Order (MANDATORY)

Before implementing ANY feature, read in order:

1. `CLAUDE.md`
2. `specs/api.md`
3. The relevant feature spec (e.g. `specs/retrieval.md`)

Do NOT proceed without reading all three. `CLAUDE.md` wins on conflict.

## 3. Architecture

```
Frontend (Next.js) ──HTTP + SSE──▶ Backend (FastAPI)
                                    │
                                    ├─▶ ChromaDB (vectors)
                                    └─▶ SQLite (chats, docs, traces)
```

Ingestion: upload → parse → chunk → embed → index. SSE progress per step.
Query: see §6 (phase-dependent).

## 4. API Contract Summary

Full schemas in `specs/api.md`. All frontend-backend interaction MUST go through these endpoints. Do NOT bypass the API layer.

| Method | Path | Returns |
|---|---|---|
| `POST` | `/api/documents/upload` | `202 JSON` |
| `GET` | `/api/documents` | `JSON` |
| `GET` | `/api/documents/{id}/progress` | **SSE** |
| `POST` | `/api/chats` | `JSON` |
| `GET` | `/api/chats` | `JSON` |
| `GET` | `/api/chats/{id}` | `JSON` |
| `DELETE` | `/api/chats/{id}` | `204` |
| `POST` | `/api/chats/{id}/messages` | **SSE** |
| `GET` | `/api/chats/{id}/traces/{trace_id}` | `JSON` |
| `GET` | `/api/health` | `JSON` |

## 5. Golden Path (phased)

| Phase | Adds |
|---|---|
| 1 | ingestion → rewrite → semantic → generate |
| 2 | BM25 (parallel to semantic) |
| 3 | RRF fusion |
| 4 | cross-encoder reranking |
| 5 | routing |
| 6 | evals |

Rules:
- Each phase must be fully working before moving to the next.
- Do NOT implement later phases early.
- Do NOT implement multiple phases at once.

## 6. Retrieval Pipeline (phase-aware)

```
Phase 1: query → rewrite → semantic                            → generate
Phase 2: query → rewrite → BM25 ∥ semantic                     → generate
Phase 3: query → rewrite → BM25 ∥ semantic → fusion            → generate
Phase 4: query → rewrite → BM25 ∥ semantic → fusion → rerank   → generate
Phase 5: route → rewrite → BM25 ∥ semantic → fusion → rerank   → generate
```

`∥` = concurrent (`asyncio.gather`). Order is fixed within each phase.

## 7. Model

Use ONLY `gpt-4o-mini` for ALL LLM tasks: generation, rewriting, routing (P5), eval (P6).

- Do NOT use any other model.
- Do NOT dynamically check model availability.
- If `gpt-4o-mini` is unavailable, STOP and ask.

Embeddings: `text-embedding-3-small`. Reranker (P4): `cross-encoder/ms-marco-MiniLM-L-6-v2` (local).

## 8. Framework Rules

Use **LlamaIndex** for: document ingestion, chunking, basic retrieval interface.
Use **OpenAI SDK directly** for: all LLM calls, embedding generation.

Do NOT:
- use LlamaIndex query engine abstractions
- hide the retrieval pipeline inside LlamaIndex
- delegate orchestration to LlamaIndex

The retrieval pipeline MUST remain explicitly implemented in our code.

## 9. Spec Adherence

Implementation MUST strictly follow `CLAUDE.md` and `specs/*.md`.

Do NOT: improvise, optimize beyond spec, introduce alternative approaches, introduce libraries beyond §14.

Only deviate if the user explicitly instructs. If unclear: STOP and ask.

## 10. Failure Philosophy (phase-aware)

Phase 1:
- semantic fails → return `"I cannot answer this question from your uploaded documents"`

Phase 2+:
- semantic fails → BM25 only
- BM25 fails → semantic only
- both fail → return the "cannot answer" message above

All phases:
- reranker fails → use fused results
- rewriter fails → use original query
- router fails → default to `"retrieve"`

Every fallback MUST: be logged (WARNING), be visible in trace (`flags` field), never be silent. Never fabricate from LLM general knowledge on a retrieve path.

## 11. Debugging & Logging

Every step MUST log: inputs, outputs, errors. No step may fail silently. Use Python `logging` + LangSmith spans per `specs/retrieval.md` §5.

## 12. Verification

After implementing any feature:

1. Test the feature in isolation.
2. Log intermediate outputs.
3. Confirm outputs match spec.

Do NOT proceed without verification.

## 13. Experimentation (per phase)

Each phase is an experiment. For every phase: observe answer quality on the same queries, observe retrieval differences vs previous phase, log findings in `docs/decisions.md`. Do NOT skip.

## 14. Tech Stack (pinned)

**Backend (Python 3.12, `uv`):** FastAPI ≥0.136, ChromaDB ≥1.5.7, OpenAI SDK ≥2.32, LlamaIndex ≥0.12, sentence-transformers ≥3.3, rank-bm25 ≥0.2.2, SQLModel ≥0.0.22, LangSmith ≥0.2, sse-starlette ≥2.1.3, pypdf, python-docx, ebooklib, markdown-it-py, tiktoken.

**Frontend (Node 20.9+, pnpm):** Next.js 16.2, shadcn/ui, zustand, `@microsoft/fetch-event-source`, react-markdown, lucide-react, sonner.

## 15. Retrieval Constants

| Constant | Value |
|---|---|
| Chunk size / overlap | 512 / 64 tokens (`cl100k_base`) |
| BM25 / semantic top-k | 10 / 10 |
| RRF k | 60 |
| Fused / reranked top-k | 10 / 3 |
| Chat history turns | 6 |
| Max file / PDF pages / docs | 50 MB / 500 / 20 |

## 16. Folder Layout (fixed)

```
rag-mvp/
├── CLAUDE.md
├── specs/{ingestion,retrieval,generation,api,frontend,evals}.md
├── Makefile  README.md  .env.example
├── docs/decisions.md
├── prompts/{router,rewrite,generation,judge_groundedness,judge_relevance}.txt
├── backend/app/{models,api,ingestion,retrieval,generation,observability}/
├── frontend/{app,components,lib,types}/
└── eval/{dataset.jsonl,run_eval.py,judges.py,results/}
```

## 17. Hard Constraints

1. No new libraries beyond §14.
2. No pipeline reordering within a phase.
3. No folder structure changes.
4. No auth, multi-tenancy, Redis, Celery, Docker.
5. No answer caching.
6. No streaming retrieval — only generation tokens stream.
7. No WebSocket — SSE only.
8. No chat history summarization — send last 6 raw messages.

## 18. When In Doubt

Missing detail → relevant `specs/*.md`. Conflict → `CLAUDE.md` wins. Still unclear → STOP and ask. Do not guess.
