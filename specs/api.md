# specs/api.md — Phase 1

> HTTP endpoints and SSE contracts. All request/response bodies are Pydantic models. All paths prefixed `/api`.

## 1. Conventions

- Errors: `{"error": "<snake_case_code>", "detail": "<human message or null>"}`.
- Timestamps: ISO 8601 UTC strings.
- IDs: UUID4 strings.
- CORS: allow `http://localhost:3000` for local dev.

## 2. Shared Models

```python
class DocumentStatus(str, Enum):
    pending = "pending"
    parsing = "parsing"
    chunking = "chunking"
    embedding = "embedding"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"

class Document(BaseModel):
    id: str
    filename: str
    content_hash: str
    mime_type: str
    size_bytes: int
    num_pages: int | None
    num_chunks: int
    status: DocumentStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime

class Chat(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"

class Message(BaseModel):
    id: str
    chat_id: str
    role: MessageRole
    content: str
    trace_id: str | None
    created_at: datetime

class Hit(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    chunk_index: int
    text: str
    source_page: int | None
    score: float
    source: Literal["semantic"]       # Phase 1

class Trace(BaseModel):
    id: str
    chat_id: str
    original_query: str
    rewritten_query: str | None
    semantic_hits: list[Hit]
    final_answer: str
    latency_ms: int
    langsmith_run_url: str | None
    flags: dict[str, bool]            # rewrite_fallback, semantic_fallback, citations_present, citation_out_of_range
    created_at: datetime
```

Phase 2+ extends `Trace` with `bm25_hits`, `fused_hits`, `reranked_hits`, and `router_decision`. Do NOT add those fields yet.

## 3. Documents

### 3.1 `POST /api/documents/upload`

**Request:** `multipart/form-data`, single field `file`.

**Response:** `202 Accepted`

```python
class UploadResponse(BaseModel):
    document_id: str
    filename: str
    status: Literal["pending"]
```

**Errors:** `400` for `unsupported_file_type`, `file_too_large`, `pdf_too_long`, `document_limit_reached`, `empty_file`. `500 storage_error`.

### 3.2 `GET /api/documents`

**Response:** `200 OK`

```python
class DocumentListResponse(BaseModel):
    documents: list[Document]         # sorted by created_at desc
```

### 3.3 `GET /api/documents/{document_id}`

**Response:** `200 OK` → `Document`
**Errors:** `404 document_not_found`

### 3.4 `GET /api/documents/{document_id}/progress`

**Response:** `200 OK`, `Content-Type: text/event-stream`

```
event: step
data: {"step":"<step>","state":"<state>","progress_pct":<0..100>,"message":<string|null>}
```

`step ∈ {upload, parse, chunk, embed, index}`, `state ∈ {running, complete, failed}`.

Terminal:
```
event: done
data: {"document_id":"...","num_chunks":<int>,"num_pages":<int|null>}

event: error
data: {"step":"<step>","error":"<code>","detail":"<message>"}
```

Stream closes after `done` or `error`.

## 4. Chats

### 4.1 `POST /api/chats`

**Request:** none.
**Response:** `201 Created` → `Chat`. `title` defaults to `"New chat"`.

### 4.2 `GET /api/chats`

**Response:** `200 OK`

```python
class ChatListResponse(BaseModel):
    chats: list[Chat]                 # sorted by updated_at desc
```

### 4.3 `GET /api/chats/{chat_id}`

**Response:** `200 OK`

```python
class ChatDetailResponse(BaseModel):
    chat: Chat
    messages: list[Message]           # oldest first
```

**Errors:** `404 chat_not_found`

### 4.4 `DELETE /api/chats/{chat_id}`

Cascades to `Message` and `Trace` rows.
**Response:** `204 No Content`
**Errors:** `404 chat_not_found`

### 4.5 `POST /api/chats/{chat_id}/messages`

**Request:**
```python
class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
```

**Response:** `200 OK`, `Content-Type: text/event-stream`

Events in this exact order:

```
event: user_message_saved
data: {"message_id":"<uuid>","chat_id":"<uuid>"}

event: trace_partial
data: {"rewritten_query":"..."}

event: trace_partial
data: {"semantic_hits":[...Hit...]}

event: token
data: {"text":"The "}

event: token
data: {"text":"answer "}

... (one event per streamed token) ...

event: done
data: {"message_id":"<uuid>","trace_id":"<uuid>","latency_ms":<int>}
```

Constraints:
- `user_message_saved` fires exactly once, before any `trace_partial`.
- `trace_partial` events fire in the order shown. Each carries a subset of the `Trace`; the frontend merges them.
- For the canned "cannot answer" branch, `trace_partial` with `semantic_hits: []` still fires, then a single `token` event with the full canned message, then `done`.
- `done` is always last. `error` replaces it on catastrophic failure.

Error (replaces `done`):
```
event: error
data: {"error":"<code>","detail":"<message>"}
```

**Errors (before stream starts):**
| Status | Code |
|---|---|
| 400 | `empty_message`, `no_documents_ready` |
| 404 | `chat_not_found` |

### 4.6 `GET /api/chats/{chat_id}/traces/{trace_id}`

**Response:** `200 OK` → `Trace` (with `semantic_hits` as `list[Hit]`, not JSON string).
**Errors:** `404 trace_not_found`

## 5. Health

### 5.1 `GET /api/health`

**Response:** `200 OK`

```python
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    chroma_ok: bool
    openai_ok: bool
    num_documents: int
```

`status="degraded"` if `chroma_ok=False` or `openai_ok=False`.

## 6. SSE Implementation Notes

- Use `sse-starlette`'s `EventSourceResponse`.
- Each `data:` payload is a single-line JSON string.
- Send keep-alive `: keep-alive\n\n` every 15s during long steps.
- Close stream promptly after `done` or `error`.
- Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`.

## 7. Not in Phase 1

- No `DELETE /api/documents/{id}`.
- No `PATCH` endpoints.
- No auth endpoints.
- No websocket endpoints.
- `Trace` schema does NOT include BM25/fused/reranked hits or router decision yet.