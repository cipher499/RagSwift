import { fetchEventSource } from "@microsoft/fetch-event-source"
import type {
  SSEUserMessageSaved,
  SSETracePartialRewrite,
  SSETracePartialHits,
  SSEToken,
  SSEDone,
  SSEError,
  SSEStepEvent,
  SSEIngestDone,
  SSEIngestError,
} from "./types"

const BASE = process.env.NEXT_PUBLIC_API_URL

export async function streamMessage(
  chatId: string,
  content: string,
  handlers: {
    onUserSaved: (d: SSEUserMessageSaved) => void
    onRewrite: (d: SSETracePartialRewrite) => void
    onHits: (d: SSETracePartialHits) => void
    onToken: (d: SSEToken) => void
    onDone: (d: SSEDone) => void
    onError: (d: SSEError | Error) => void
  },
  signal: AbortSignal
): Promise<void> {
  await fetchEventSource(`${BASE}/api/chats/${chatId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
    signal,
    onmessage(ev) {
      let data: unknown
      try {
        data = JSON.parse(ev.data)
      } catch (err) {
        handlers.onError(err instanceof Error ? err : new Error(String(err)))
        return
      }

      switch (ev.event) {
        case "user_message_saved":
          handlers.onUserSaved(data as SSEUserMessageSaved)
          break
        case "trace_partial": {
          const d = data as Record<string, unknown>
          if ("rewritten_query" in d) {
            handlers.onRewrite(d as unknown as SSETracePartialRewrite)
          } else if ("semantic_hits" in d) {
            handlers.onHits(d as unknown as SSETracePartialHits)
          }
          break
        }
        case "token":
          handlers.onToken(data as SSEToken)
          break
        case "done":
          handlers.onDone(data as SSEDone)
          break
        case "error":
          handlers.onError(data as SSEError)
          break
      }
    },
    onerror(err) {
      handlers.onError(err instanceof Error ? err : new Error(String(err)))
      // rethrow to stop fetchEventSource from retrying
      throw err
    },
  })
}

export async function subscribeIngestionProgress(
  docId: string,
  handlers: {
    onStep: (d: SSEStepEvent) => void
    onDone: (d: SSEIngestDone) => void
    onError: (d: SSEIngestError) => void
  },
  signal: AbortSignal
): Promise<void> {
  await fetchEventSource(`${BASE}/api/documents/${docId}/progress`, {
    method: "GET",
    signal,
    onmessage(ev) {
      let data: unknown
      try {
        data = JSON.parse(ev.data)
      } catch {
        return
      }

      switch (ev.event) {
        case "step":
          handlers.onStep(data as SSEStepEvent)
          break
        case "done":
          handlers.onDone(data as SSEIngestDone)
          break
        case "error":
          handlers.onError(data as SSEIngestError)
          break
      }
    },
    onerror(err) {
      // log but don't bubble — ingestion errors come via the error event
      console.error("Ingestion SSE connection error:", err)
      throw err
    },
  })
}
