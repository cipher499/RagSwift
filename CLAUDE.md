# CLAUDE.md — RAG MVP Stage I

> Single source of truth. Specs in `specs/`. **`CLAUDE.md` wins on any conflict.**

## 1. Purpose

Single-user, no-auth RAG app: upload docs, watch ingestion, ask questions, get grounded answers with visible retrieval internals, resume chats.

## 2. Required Reading (MANDATORY)

Before any implementation, read in order: `CLAUDE.md` → `specs/api.md` → relevant feature spec. Do NOT write code without completing all three.

## 3. Architecture

```
Frontend (Next.js) ──HTTP + SSE──▶ Backend (FastAPI)
                                    ├─▶ ChromaDB  └─▶ SQLite
```

All frontend-backend interaction via defined API endpoints only. Full contract in `specs/api.md`.

## 4. Phases

| Phase | Adds |
|---|---|
| 1 | ingestion → rewrite → semantic → generate |
| 2 | BM25 + parallel retrieval + RRF fusion |
| 3 | Cohere reranking |
| 4 | routing |
| 5 | evals |

- Fully verify each phase before starting the next.
- Never implement multiple phases at once or skip ahead.

## 5. Retrieval Pipeline

```
P1: query → rewrite → semantic                          → generate
P2: query → rewrite → BM25 ∥ semantic → fusion          → generate
P3: query → rewrite → BM25 ∥ semantic → fusion → rerank → generate
P4: route → rewrite → BM25 ∥ semantic → fusion → rerank → generate
```

`∥` = `asyncio.gather`. Order is fixed per phase. Full contracts in `specs/retrieval.md`.

## 6. Models

| Role | Model |
|---|---|
| LLM (all tasks) | `gpt-4o-mini` — no substitutions |
| Embeddings | `text-embedding-3-small` |
| Reranker (P3+) | Cohere `rerank-english-v3.0` |

If `gpt-4o-mini` unavailable: STOP and ask.

## 7. Framework Rules

- **LlamaIndex:** ingestion, chunking, basic retrieval interface only.
- **OpenAI SDK directly:** all LLM calls and embeddings.
- Do NOT use LlamaIndex query engines or hide the pipeline inside LlamaIndex.
- Retrieval orchestration stays in our code, explicit and visible.

## 8. Failure Philosophy

- P1: semantic fails → canned `"I cannot answer this question from your uploaded documents"`.
- P2+: one retriever fails → use the other (fuse over single list). Both fail → canned message.
- All phases: reranker fails → `fused_hits[:RERANK_TOP_K]`; rewriter fails → original query; router fails → `"retrieve"`.
- Every fallback: log WARNING + set flag in trace. Never silent. Never fabricate.

## 9. Spec Adherence

Follow specs strictly. Do NOT improvise, optimize beyond spec, or add libraries beyond §11. Deviate only on explicit user instruction. If unclear: STOP and ask.

## 10. Verification & Experimentation

- After every feature: test in isolation, log intermediate outputs, confirm against spec.
- Every step logs inputs, outputs, errors. No silent failures. Use `logging` + LangSmith spans.
- After every phase: compare quality vs previous phase, log findings in `docs/decisions.md`.

## 11. Tech Stack

**Backend (Python 3.12, `uv`):** `fastapi ≥0.136`, `chromadb ≥1.5.7`, `openai ≥2.32`, `llama-index ≥0.12`, `rank-bm25 ≥0.2.2`, `cohere ≥5.0`, `sqlmodel ≥0.0.22`, `langsmith ≥0.2`, `sse-starlette ≥2.1.3`, `pypdf`, `python-docx`, `ebooklib`, `markdown-it-py`, `tiktoken`.

**Frontend (Node 20.9+, pnpm):** `next 16.2`, `shadcn/ui`, `zustand`, `@microsoft/fetch-event-source`, `react-markdown`, `lucide-react`, `sonner`.

## 12. Retrieval Constants

Defined in `backend/app/retrieval/constants.py`. Import from there — never hardcode.

| `SEMANTIC_TOP_K` | `BM25_TOP_K` | `RRF_K` | `FUSED_TOP_K` | `RERANK_TOP_K` |
|---|---|---|---|---|
| 20 | 20 | 60 | 10 | 3 |

Other constants: chunk 512/64 tokens, chat history 6 turns, max 50 MB / 500 pages / 20 docs.

## 13. Folder Layout (fixed)

```
rag-mvp/
├── CLAUDE.md
├── specs/{ingestion,retrieval,generation,api,frontend,evals}.md
├── Makefile  README.md  .env.example  docs/decisions.md
├── prompts/{router,rewrite,generation,judge_groundedness,judge_relevance}.txt
├── backend/app/{models,api,ingestion,retrieval,generation,observability}/
├── frontend/{app,components,lib,types}/
└── eval/{dataset.jsonl,run_eval.py,judges.py,results/}
```

## 14. Hard Constraints

1. No libraries beyond §11.
2. No pipeline reordering within a phase.
3. No folder structure changes.
4. No auth, multi-tenancy, Redis, Celery, Docker.
5. No answer caching.
6. Retrieval does not stream — only generation tokens stream.
7. SSE only — no WebSocket.
8. Last 6 raw messages to LLM — no summarization.