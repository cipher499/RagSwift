import type { Chat, Document, Message, Trace } from "./types"

const BASE = process.env.NEXT_PUBLIC_API_URL

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? body.error ?? detail
    } catch {
      // ignore parse failure
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  uploadDocument: (file: File) => {
    const form = new FormData()
    form.append("file", file)
    return request<{ document_id: string; filename: string; status: string }>(
      "/api/documents/upload",
      { method: "POST", body: form }
    )
  },

  listDocuments: () =>
    request<{ documents: Document[] }>("/api/documents"),

  createChat: () =>
    request<Chat>("/api/chats", { method: "POST" }),

  listChats: () =>
    request<{ chats: Chat[] }>("/api/chats"),

  getChat: (id: string) =>
    request<{ chat: Chat; messages: Message[] }>(`/api/chats/${id}`),

  deleteChat: (id: string) =>
    request<void>(`/api/chats/${id}`, { method: "DELETE" }),

  getTrace: (chatId: string, traceId: string) =>
    request<Trace>(`/api/chats/${chatId}/traces/${traceId}`),

  health: () =>
    request<{
      status: string
      chroma_ok: boolean
      openai_ok: boolean
      num_documents: number
    }>("/api/health"),
}
