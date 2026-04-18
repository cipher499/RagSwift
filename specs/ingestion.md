# specs/ingestion.md — Phase 1

> Ingestion pipeline. Reads `CLAUDE.md` §8 (LlamaIndex for ingestion/chunking), §10 (Failure Philosophy), §11 (Logging), §15 (Constants).

## 1. Pipeline

```
upload → parse → chunk → embed → index → ready
```

Each step emits one SSE event on start (`state="running"`) and one on completion (`state="complete"` or `"failed"`). All transitions write an `IngestionEvent` row to SQLite.

## 2. Supported Formats

PDF, EPUB, DOCX, MD, TXT. Any other extension → `400 unsupported_file_type`.

Use LlamaIndex `SimpleDirectoryReader` with a temporary directory containing the single uploaded file. It handles all five formats natively. Do NOT write custom parsers.

## 3. Function Contracts

### 3.1 `parse_document`

```python
from llama_index.core import SimpleDirectoryReader
from llama_index.core.schema import Document as LIDocument

def parse_document(file_path: Path) -> list[LIDocument]: ...
```

- Use `SimpleDirectoryReader(input_files=[file_path]).load_data()`.
- If return list is empty OR all documents have empty `text`, raise `IngestionError("no extractable text")`.
- Do NOT OCR. Scanned PDFs fail with the above message.

### 3.2 `chunk_document`

```python
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode

def chunk_document(documents: list[LIDocument], document_id: str) -> list[TextNode]: ...
```

- Use `SentenceSplitter(chunk_size=512, chunk_overlap=64, tokenizer=tiktoken.encoding_for_model("gpt-4o-mini").encode)`.
- Call `splitter.get_nodes_from_documents(documents)`.
- For each returned `TextNode`, set `node.id_ = f"{document_id}:{index:04d}"` (override LlamaIndex's default UUID).
- Set `node.metadata` to include: `{document_id, filename, chunk_index, source_page (if present from parser)}`.
- Return the nodes. Do NOT use LlamaIndex's `IngestionPipeline` abstraction — call the splitter directly.

### 3.3 `embed_chunks`

```python
from openai import AsyncOpenAI

async def embed_chunks(nodes: list[TextNode]) -> list[list[float]]: ...
```

- Use OpenAI SDK directly (`AsyncOpenAI().embeddings.create`). Do NOT use LlamaIndex's embedding wrappers.
- Model: `text-embedding-3-small`.
- Batch up to 100 chunks per API call.
- Retry on rate limit: 3 attempts with exponential backoff (1s, 2s, 4s).
- If all retries fail → raise `IngestionError("embedding service unavailable")`.

### 3.4 `index_chunks`

```python
import chromadb

async def index_chunks(nodes: list[TextNode], embeddings: list[list[float]]) -> None: ...
```

- Use `chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)` directly. Do NOT use LlamaIndex's `ChromaVectorStore` wrapper.
- Collection: `rag_stage1` (create if missing).
- Upsert with: `ids=[node.id_]`, `embeddings=...`, `documents=[node.text]`, `metadatas=[node.metadata]`.

## 4. SSE Progress Contract

`GET /api/documents/{doc_id}/progress` returns `text/event-stream`:

```
event: step
data: {"step":"<step>","state":"<state>","progress_pct":<0..100>,"message":<string|null>}
```

Where `step ∈ {upload, parse, chunk, embed, index}` and `state ∈ {running, complete, failed}`.

Terminal:
```
event: done
data: {"document_id":"...","num_chunks":<int>,"num_pages":<int|null>}

event: error
data: {"step":"<step>","error":"<code>","detail":"<message>"}
```

Stream closes after `done` or `error`.

## 5. Upload Validation

Before queuing background task:

| Check | Failure |
|---|---|
| Extension in {pdf, epub, docx, md, txt} | `400 unsupported_file_type` |
| Size ≤ 50 MB | `400 file_too_large` |
| PDF pages ≤ 500 (probe with `pypdf.PdfReader`) | `400 pdf_too_long` |
| Total documents in collection < 20 | `400 document_limit_reached` |

## 6. Duplicate Handling

On upload, compute SHA-256 of file bytes. If a `Document` with same `content_hash` exists:

1. Delete its chunks: `collection.delete(where={"document_id": existing_id})`.
2. Delete `Document` row and its `IngestionEvent` rows.
3. Proceed with new upload as if old one never existed.

Log INFO: `duplicate_overwrite document_id={new_id} replaced={old_id}`.

## 7. Edge Cases

| Case | Behavior |
|---|---|
| Zero extractable text | Fail at `parse` with `"no extractable text"`. |
| Zero chunks produced | Fail at `chunk` with `"no chunks produced"`. |
| OpenAI embedding 429 after retries | Fail at `embed`. Status → `failed`. |
| Chroma upsert exception | Fail at `index`. Status → `failed`. |
| Duplicate content | Overwrite per §6. |

## 8. Success Criteria (Phase 1)

- A 50-page PDF completes all 5 steps in under 60s on a standard laptop.
- `Document.status` transitions strictly monotonic: `pending → parsing → chunking → embedding → indexing → ready` (or `failed`, terminal).
- Every step emits exactly one running event and exactly one terminal event.
- Re-uploading identical bytes produces the same `num_chunks` (±1 tokenizer nondeterminism).

## 9. LangSmith Spans

```
ingest_document (root)
├── parse      (attributes: num_documents, num_pages?)
├── chunk      (attributes: num_nodes, total_tokens)
├── embed      (attributes: num_batches, total_tokens, latency_ms)
└── index      (attributes: chunks_upserted, latency_ms)
```

## 10. What Phase 1 Does NOT Include

- No BM25 index. Do NOT build `rank_bm25` structures yet.
- No semantic chunking. `SentenceSplitter` (fixed 512/64) is the only strategy.
- No section-aware chunking beyond what `SimpleDirectoryReader` provides in metadata.
- No chunking fallback logic (nothing to fall back to — `SentenceSplitter` is already the simple path).