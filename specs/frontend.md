# specs/frontend.md — Phase 1

> Frontend spec. Reads CLAUDE.md §3 (Architecture), §4 (API Contract), §17 (Hard Constraints).
> Do NOT modify backend or API contracts. Do NOT introduce libraries beyond §14.

---

## 1. Overview

Single-page app. Three columns: sidebar (chats), main (upload or chat), trace panel (debug).
All data comes from the backend. No client-side business logic.

---

## 2. Tech Stack

| Layer | Choice |
|---|---|
| Framework | Next.js 16.2 App Router, TypeScript |
| Styling | Tailwind utility classes only — no custom abstractions |
| Components | shadcn/ui: `button`, `card`, `input`, `textarea`, `badge`, `separator`, `scroll-area`, `collapsible`, `skeleton`, `tooltip` |
| Global state | Zustand — one store, flat shape (§5) |
| SSE client | `@microsoft/fetch-event-source` — supports POST + headers; native EventSource does not |
| Markdown | `react-markdown` + `remark-gfm` |
| Icons | `lucide-react` |
| Toast | `sonner` |

Install:
```bash
pnpm create next-app@latest frontend --typescript --tailwind --app --yes
cd frontend
pnpm add @microsoft/fetch-event-source react-markdown remark-gfm zustand sonner lucide-react
pnpm dlx shadcn@latest init
pnpm dlx shadcn@latest add button card input textarea badge separator scroll-area collapsible skeleton tooltip
```

---

## 3. Folder Layout

```
frontend/
├── app/
│   ├── layout.tsx          # root layout: sidebar + main + trace panel
│   ├── page.tsx            # shows upload empty state or redirects to active chat
│   └── globals.css
├── components/
│   ├── sidebar.tsx         # chat list + new chat button
│   ├── upload-panel.tsx    # drag-drop zone + ingestion cards
│   ├── ingestion-card.tsx  # one card per uploading document
│   ├── chat-area.tsx       # message list + input bar
│   ├── message.tsx         # single message bubble
│   ├── trace-panel.tsx     # rewritten query + hits + flags
│   └── ui/                 # shadcn-generated
├── lib/
│   ├── api.ts              # typed fetch wrappers (no raw fetch elsewhere)
│   ├── sse.ts              # SSE client: streamMessage() + subscribeIngestionProgress()
│   ├── store.ts            # zustand store
│   └── types.ts            # mirrors backend Pydantic schemas exactly
└── .env.local              # NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Rule: raw `fetch` and `fetchEventSource` only in `lib/api.ts` and `lib/sse.ts`. Components never call fetch directly.

---

## 4. Types (`lib/types.ts`)

Mirror `specs/api.md §2` exactly. No extra fields.

```ts
export type DocumentStatus = "pending"|"parsing"|"chunking"|"embedding"|"indexing"|"ready"|"failed"

export interface Document {
  id: string; filename: string; content_hash: string; mime_type: string
  size_bytes: number; num_pages: number|null; num_chunks: number
  status: DocumentStatus; error_message: string|null
  created_at: string; updated_at: string
}

export interface Chat { id: string; title: string; created_at: string; updated_at: string }

export type MessageRole = "user"|"assistant"

export interface Message {
  id: string; chat_id: string; role: MessageRole; content: string
  trace_id: string|null; created_at: string
}

export interface Hit {
  chunk_id: string; document_id: string; filename: string
  chunk_index: number; text: string; source_page: number|null
  score: number; source: "semantic"
}

export interface Trace {
  id: string; chat_id: string; original_query: string
  rewritten_query: string|null; semantic_hits: Hit[]
  final_answer: string; latency_ms: number
  langsmith_run_url: string|null; flags: Record<string, boolean>
  created_at: string
}

// SSE payloads — chat
export interface SSEUserMessageSaved { message_id: string; chat_id: string }
export interface SSETracePartialRewrite { rewritten_query: string }
export interface SSETracePartialHits { semantic_hits: Hit[] }
export interface SSEToken { text: string }
export interface SSEDone { message_id: string; trace_id: string; latency_ms: number }
export interface SSEError { error: string; detail: string }

// SSE payloads — ingestion
export type IngestionStep = "upload"|"parse"|"chunk"|"embed"|"index"
export type StepState = "pending"|"running"|"complete"|"failed"
export interface SSEStepEvent { step: IngestionStep; state: StepState; progress_pct: number; message: string|null }
export interface SSEIngestDone { document_id: string; num_chunks: number; num_pages: number|null }
export interface SSEIngestError { step: IngestionStep; error: string; detail: string }
```

---

## 5. State (`lib/store.ts`)

Flat Zustand store. No nested slices. No derived state computed inside the store.

```ts
interface AppState {
  // documents
  documents: Document[]
  ingestionSteps: Record<string, Record<IngestionStep, StepState>>  // doc_id → step → state

  // chats
  chats: Chat[]
  activeChatId: string | null
  messages: Record<string, Message[]>      // chat_id → messages
  traces: Record<string, Trace>            // trace_id → Trace

  // active streaming turn
  streamingChatId: string | null
  partialTokens: string                    // accumulating answer text
  partialTrace: Partial<Trace>             // built from trace_partial events

  // actions
  setDocuments: (docs: Document[]) => void
  upsertDocument: (doc: Document) => void
  setStepState: (docId: string, step: IngestionStep, state: StepState) => void
  setChats: (chats: Chat[]) => void
  prependChat: (chat: Chat) => void
  setActiveChatId: (id: string | null) => void
  setMessages: (chatId: string, messages: Message[]) => void
  appendMessage: (chatId: string, msg: Message) => void
  setTrace: (traceId: string, trace: Trace) => void
  startStream: (chatId: string) => void
  appendToken: (text: string) => void
  mergeTracePartial: (data: Partial<Trace>) => void
  finalizeStream: (msg: Message, trace: Trace) => void
  clearStream: () => void
}
```

`finalizeStream`: appends completed assistant `Message` to `messages[chatId]`, stores `trace` in `traces[trace.id]`, calls `clearStream`.
`clearStream`: resets `streamingChatId`, `partialTokens`, `partialTrace` to initial values.

---

## 6. API Client (`lib/api.ts`)

All functions throw on non-2xx. Callers handle errors with try/catch + toast.

```ts
const BASE = process.env.NEXT_PUBLIC_API_URL

export const api = {
  uploadDocument: (file: File) => Promise<{ document_id: string; filename: string; status: string }>
  listDocuments:  () => Promise<{ documents: Document[] }>
  createChat:     () => Promise<Chat>
  listChats:      () => Promise<{ chats: Chat[] }>
  getChat:        (id: string) => Promise<{ chat: Chat; messages: Message[] }>
  deleteChat:     (id: string) => Promise<void>
  getTrace:       (chatId: string, traceId: string) => Promise<Trace>
  health:         () => Promise<{ status: string; chroma_ok: boolean; openai_ok: boolean; num_documents: number }>
}
```

---

## 7. SSE Client (`lib/sse.ts`)

```ts
export async function streamMessage(
  chatId: string,
  content: string,
  handlers: {
    onUserSaved: (d: SSEUserMessageSaved) => void
    onRewrite:   (d: SSETracePartialRewrite) => void
    onHits:      (d: SSETracePartialHits) => void
    onToken:     (d: SSEToken) => void
    onDone:      (d: SSEDone) => void
    onError:     (d: SSEError | Error) => void
  },
  signal: AbortSignal
): Promise<void>
```

Implementation rules:
- Parse each `ev.data` with `JSON.parse`. On parse failure: call `onError`, return.
- Route by `ev.event`: `user_message_saved` → `onUserSaved`; `trace_partial` → check keys (see below); `token` → `onToken`; `done` → `onDone`; `error` → `onError`.
- `trace_partial` disambiguation: `"rewritten_query" in data` → `onRewrite`; `"semantic_hits" in data` → `onHits`.
- On `fetchEventSource` throw: call `onError(err)`.

```ts
export async function subscribeIngestionProgress(
  docId: string,
  handlers: {
    onStep:  (d: SSEStepEvent) => void
    onDone:  (d: SSEIngestDone) => void
    onError: (d: SSEIngestError) => void
  },
  signal: AbortSignal
): Promise<void>
```

---

## 8. Component Architecture

### 8.1 Layout (`app/layout.tsx`)

```
┌────────────┬───────────────────────────────┬──────────────────────┐
│  Sidebar   │         Main column           │    Trace Panel       │
│  240px     │         flex-1                │    320px             │
│  fixed     │                               │    collapsible       │
└────────────┴───────────────────────────────┴──────────────────────┘
```

- Sidebar always visible on ≥ 1024px. Sheet drawer on mobile.
- Trace panel: hidden until first assistant message arrives. Toggle button top-right.
- Main column: `<UploadPanel>` when `activeChatId === null`; `<ChatArea>` otherwise.

### 8.2 Sidebar (`components/sidebar.tsx`)

- On mount: `api.listChats()` → `setChats`. `api.listDocuments()` → `setDocuments`.
- "New chat" button → `api.createChat()` → `prependChat` + `setActiveChatId`.
- Chat list ordered by `updated_at` desc. Active item highlighted.
- Click chat → `setActiveChatId(id)` + `api.getChat(id)` → `setMessages`.

### 8.3 Upload Panel (`components/upload-panel.tsx`)

- Drag-drop zone + click-to-browse. Accept: `.pdf,.epub,.docx,.md,.txt`. Multiple files.
- On drop/select per file: `api.uploadDocument(file)` → `upsertDocument` → `subscribeIngestionProgress(doc_id, ...)`.
- One `<IngestionCard>` per in-progress or recently completed document.
- When any document is `ready`: banner **"Ready to chat. Ask a question →"** — clicking creates new chat.

### 8.4 Ingestion Card (`components/ingestion-card.tsx`)

Five step pills: `upload → parse → chunk → embed → index`.

| State | Visual |
|---|---|
| `pending` | gray outline |
| `running` | blue fill + spinner |
| `complete` | green fill + check |
| `failed` | red fill + X + tooltip with `error` string |

On `done` event: collapse to single row `✓ filename · N chunks` after 1.5s delay.
On `error` event: mark failed step red; show `detail` in tooltip. Never auto-hide.

### 8.5 Chat Area (`components/chat-area.tsx`)

- On `activeChatId` change: `api.getChat(id)` → `setMessages`. Show skeletons during fetch.
- Renders `<Message>` for each item in `messages[activeChatId]`.
- During stream: renders extra `<Message role="assistant" content={partialTokens}>` with pulsing `▌` cursor.
- Auto-scrolls to bottom on new message and on each `appendToken`.
- Input: `<Textarea>` auto-grow 1–6 rows. Submit: `Cmd/Ctrl+Enter` or button.
- Disabled with tooltip `"Upload a document first"` when no document has `status === "ready"`.
- Disabled during active stream. Send button replaced with spinner.
- On submit: `store.startStream(chatId)` → `streamMessage(...)` with handlers wired to store actions.
- On `done`: `api.getTrace(chatId, trace_id)` → `finalizeStream(msg, trace)`.
- On `error` event or throw: `clearStream()` + `toast.error(detail)`.

### 8.6 Message (`components/message.tsx`)

- User: right-aligned, muted background.
- Assistant: left-aligned, `react-markdown` + `remark-gfm`.
- `[N]` tokens: render as `<Badge>` pill. On click: open trace panel + scroll to hit index `N-1`.
- Sources strip below each completed assistant message (if trace available): `[1] filename · p.N` per hit.
- Content starting with `"[Generation interrupted]"`: render in destructive color.

### 8.7 Trace Panel (`components/trace-panel.tsx`)

Four `<Collapsible>` sections, all open by default. Populates progressively during stream — does not wait for `done`.

**1. Rewrite**
- "Rewritten query:" → `partialTrace.rewritten_query`
- If `flags.rewrite_fallback`: yellow badge `⚠ rewrite fallback — original query used`

**2. Semantic Hits**
- Table: rank | score (2 dp) | filename | page | first 120 chars of text (expandable to full)
- Each row anchors to `id="hit-{index}"` for citation scroll targeting
- Empty state: `"No hits retrieved"` in muted text
- If `flags.semantic_fallback`: yellow badge `⚠ semantic fallback`

**3. Flags**
- Each key in `flags`: true → yellow badge, false → gray badge

**4. Meta**
- `latency_ms` display
- `langsmith_run_url`: external link if present

---

## 9. Data Flow

### 9.1 Upload + Ingestion

```
User drops file
→ api.uploadDocument(file) → POST /api/documents/upload → { document_id }
→ upsertDocument({ status: "pending", ... })
→ subscribeIngestionProgress(doc_id, handlers, signal)
  → GET /api/documents/{id}/progress (SSE)
    event: step  → setStepState(doc_id, step, state) → pill updates
    event: done  → upsertDocument({ status: "ready", num_chunks }) → card collapses → banner appears
    event: error → setStepState(doc_id, step, "failed") → red pill + toast.error
```

### 9.2 Send Message + Stream

```
User submits question
→ store.startStream(chatId)
→ streamMessage(chatId, content, handlers, signal)
  → POST /api/chats/{id}/messages (SSE)

  user_message_saved → appendMessage(chatId, { role: "user", content })
  trace_partial { rewritten_query } → mergeTracePartial → trace panel §1 updates
  trace_partial { semantic_hits }   → mergeTracePartial → trace panel §2 updates
  token { text } → appendToken(text) → streaming bubble grows
  done { message_id, trace_id, latency_ms }
    → api.getTrace(chatId, trace_id) → full Trace
    → finalizeStream(assistantMessage, trace)
    → streaming bubble replaced by persisted message
    → trace panel §3 + §4 populate

  error → clearStream() + toast.error(detail)
```

### 9.3 Load Existing Chat

```
User clicks chat in sidebar
→ setActiveChatId(id)
→ api.getChat(id) → { chat, messages }
→ setMessages(id, messages)
→ if last assistant message has trace_id:
    api.getTrace(id, trace_id) → setTrace(trace_id, trace) → trace panel populates
```

---

## 10. Error Handling

- All `api.*` calls: try/catch → `toast.error(err.message)`. Never swallow.
- SSE `error` event: `clearStream()` + `toast.error(detail)`.
- SSE connection drop (fetchEventSource throw): inline banner in chat area `"Connection lost. Refresh to retry."`.
- Backend `status: "degraded"` from `/api/health` on mount: persistent top banner `"Service degraded — check backend logs."`.
- Ingestion failed step: red pill with tooltip. Does not disappear automatically.

---

## 11. Success Criteria

1. Upload PDF → all 5 pills transition `pending → running → complete`. Card collapses to summary row.
2. Ready banner appears after ingestion. Clicking it creates a new chat.
3. Send question → rewritten query appears in trace panel before first token arrives.
4. Tokens stream progressively into bubble. Cursor visible during stream.
5. `done` event → bubble replaced by final markdown-rendered message with citation badges.
6. Trace panel shows hits with scores, filenames, page numbers.
7. Refresh → chats + messages + traces restored from backend. No lost state.
8. Input disabled with tooltip when no ready documents.
9. Citation badge click → trace panel opens, scrolls to correct hit row.
10. All error states visible. Zero silent failures.

---

## 12. Testing Checklist

Run manually in order:

1. **Upload** → drop PDF → verify all 5 pills complete → card collapses.
2. **Upload error** → drop `.zip` → verify toast, no card added.
3. **New chat** → click "New chat" → appears in sidebar, empty chat area shown.
4. **Send query** → verify SSE sequence: rewritten query in trace → hits in trace → tokens stream → done finalises.
5. **Canned response** → `make reset-data`, restart backend, send query → exact canned message rendered.
6. **Fallback flags** → set bad `OPENAI_API_KEY`, send query → `rewrite_fallback` yellow badge in trace panel.
7. **Multiple chats** → create 2 chats, send messages in each → switching shows correct messages and trace.
8. **Refresh** → send message, refresh → chat + trace restored.
9. **Trace panel toggle** → collapse and reopen → state preserved.
10. **Citation click** → click `[1]` badge → trace panel scrolls to hit row 0.

---

## 13. Not in Phase 1

- No dark mode toggle.
- No chat rename.
- No document deletion UI.
- No copy / regenerate buttons.
- No token or cost counter.
- No keyboard shortcuts beyond `Cmd/Ctrl+Enter`.
- No auth.
