import { create } from "zustand";
import type { Chat, Document, Message, Trace } from "@/types";

interface AppStore {
  // Data
  chats: Chat[];
  activeChatId: string | null;
  messages: Record<string, Message[]>;
  documents: Document[];
  traces: Record<string, Trace>;

  // UI
  activeTraceId: string | null;
  activeTraceChatId: string | null;

  // Chat actions
  setChats(chats: Chat[]): void;
  prependChat(chat: Chat): void;
  removeChat(id: string): void;
  setActiveChatId(id: string | null): void;

  // Message actions
  setMessages(chatId: string, msgs: Message[]): void;
  addMessage(chatId: string, msg: Message): void;
  updateMessage(chatId: string, msgId: string, patch: Partial<Message>): void;

  // Document actions
  setDocuments(docs: Document[]): void;
  upsertDocument(doc: Document): void;

  // Trace actions
  setTrace(traceId: string, trace: Trace): void;
  openTrace(traceId: string, chatId: string): void;
  closeTrace(): void;
}

export const useAppStore = create<AppStore>((set) => ({
  chats: [],
  activeChatId: null,
  messages: {},
  documents: [],
  traces: {},
  activeTraceId: null,
  activeTraceChatId: null,

  setChats: (chats) => set({ chats }),

  prependChat: (chat) =>
    set((s) => ({ chats: [chat, ...s.chats] })),

  removeChat: (id) =>
    set((s) => ({
      chats: s.chats.filter((c) => c.id !== id),
      activeChatId: s.activeChatId === id ? null : s.activeChatId,
    })),

  setActiveChatId: (activeChatId) => set({ activeChatId }),

  setMessages: (chatId, msgs) =>
    set((s) => ({ messages: { ...s.messages, [chatId]: msgs } })),

  addMessage: (chatId, msg) =>
    set((s) => ({
      messages: {
        ...s.messages,
        [chatId]: [...(s.messages[chatId] ?? []), msg],
      },
    })),

  updateMessage: (chatId, msgId, patch) =>
    set((s) => ({
      messages: {
        ...s.messages,
        [chatId]: (s.messages[chatId] ?? []).map((m) =>
          m.id === msgId ? { ...m, ...patch } : m
        ),
      },
    })),

  setDocuments: (documents) => set({ documents }),

  upsertDocument: (doc) =>
    set((s) => {
      const idx = s.documents.findIndex((d) => d.id === doc.id);
      if (idx >= 0) {
        const docs = [...s.documents];
        docs[idx] = doc;
        return { documents: docs };
      }
      return { documents: [doc, ...s.documents] };
    }),

  setTrace: (traceId, trace) =>
    set((s) => ({ traces: { ...s.traces, [traceId]: trace } })),

  openTrace: (traceId, chatId) =>
    set({ activeTraceId: traceId, activeTraceChatId: chatId }),

  closeTrace: () => set({ activeTraceId: null, activeTraceChatId: null }),
}));
