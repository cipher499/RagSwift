import type { Chat, Document, Message, Trace } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// Documents

export async function getDocuments(): Promise<Document[]> {
  const data = await request<{ documents: Document[] }>("/api/documents");
  return data.documents;
}

export async function uploadDocument(file: File): Promise<{ document_id: string; filename: string; status: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/api/documents/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// Chats

export async function getChats(): Promise<Chat[]> {
  const data = await request<{ chats: Chat[] }>("/api/chats");
  return data.chats;
}

export async function createChat(): Promise<Chat> {
  return request<Chat>("/api/chats", { method: "POST" });
}

export async function getChat(id: string): Promise<{ chat: Chat; messages: Message[] }> {
  return request<{ chat: Chat; messages: Message[] }>(`/api/chats/${id}`);
}

export async function deleteChat(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/chats/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
}

export async function getTrace(chatId: string, traceId: string): Promise<Trace> {
  return request<Trace>(`/api/chats/${chatId}/traces/${traceId}`);
}

export async function getHealth(): Promise<{ status: string; chroma_ok: boolean; openai_ok: boolean; num_documents: number }> {
  return request("/api/health");
}

export { API_URL };
