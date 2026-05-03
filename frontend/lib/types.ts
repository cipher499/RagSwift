export type DocumentStatus =
  | "pending"
  | "parsing"
  | "chunking"
  | "embedding"
  | "indexing"
  | "ready"
  | "failed"

export interface Document {
  id: string
  filename: string
  content_hash: string
  mime_type: string
  size_bytes: number
  num_pages: number | null
  num_chunks: number
  status: DocumentStatus
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface Chat {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export type MessageRole = "user" | "assistant"

export interface Message {
  id: string
  chat_id: string
  role: MessageRole
  content: string
  trace_id: string | null
  created_at: string
}

export interface Hit {
  chunk_id: string
  document_id: string
  filename: string
  chunk_index: number
  text: string
  source_page: number | null
  score: number
  source: "semantic"
}

export interface Trace {
  id: string
  chat_id: string
  original_query: string
  rewritten_query: string | null
  semantic_hits: Hit[]
  final_answer: string
  latency_ms: number
  langsmith_run_url: string | null
  flags: Record<string, boolean>
  created_at: string
}

// SSE payloads — chat
export interface SSEUserMessageSaved {
  message_id: string
  chat_id: string
}

export interface SSETracePartialRewrite {
  rewritten_query: string
}

export interface SSETracePartialHits {
  semantic_hits: Hit[]
}

export interface SSEToken {
  text: string
}

export interface SSEDone {
  message_id: string
  trace_id: string
  latency_ms: number
}

export interface SSEError {
  error: string
  detail: string
}

// SSE payloads — ingestion
export type IngestionStep = "upload" | "parse" | "chunk" | "embed" | "index"
export type StepState = "pending" | "running" | "complete" | "failed"

export interface SSEStepEvent {
  step: IngestionStep
  state: StepState
  progress_pct: number
  message: string | null
}

export interface SSEIngestDone {
  document_id: string
  num_chunks: number
  num_pages: number | null
}

export interface SSEIngestError {
  step: IngestionStep
  error: string
  detail: string
}
