import { create } from "zustand"
import type {
  Document,
  Chat,
  Message,
  Trace,
  IngestionStep,
  StepState,
} from "./types"

interface AppState {
  // documents
  documents: Document[]
  ingestionSteps: Record<string, Record<IngestionStep, StepState>>

  // chats
  chats: Chat[]
  activeChatId: string | null
  messages: Record<string, Message[]>
  traces: Record<string, Trace>

  // active streaming turn
  streamingChatId: string | null
  partialTokens: string
  partialTrace: Partial<Trace>

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

const INGESTION_STEPS: IngestionStep[] = ["upload", "parse", "chunk", "embed", "index"]

function makeDefaultSteps(): Record<IngestionStep, StepState> {
  return Object.fromEntries(
    INGESTION_STEPS.map((s) => [s, "pending" as StepState])
  ) as Record<IngestionStep, StepState>
}

export const useStore = create<AppState>((set) => ({
  // initial state
  documents: [],
  ingestionSteps: {},
  chats: [],
  activeChatId: null,
  messages: {},
  traces: {},
  streamingChatId: null,
  partialTokens: "",
  partialTrace: {},

  // document actions
  setDocuments: (docs) => set({ documents: docs }),

  upsertDocument: (doc) =>
    set((state) => {
      const exists = state.documents.find((d) => d.id === doc.id)
      const documents = exists
        ? state.documents.map((d) => (d.id === doc.id ? doc : d))
        : [...state.documents, doc]
      const ingestionSteps = { ...state.ingestionSteps }
      if (!ingestionSteps[doc.id]) {
        ingestionSteps[doc.id] = makeDefaultSteps()
      }
      return { documents, ingestionSteps }
    }),

  setStepState: (docId, step, stepState) =>
    set((state) => {
      const existing = state.ingestionSteps[docId] ?? makeDefaultSteps()
      return {
        ingestionSteps: {
          ...state.ingestionSteps,
          [docId]: { ...existing, [step]: stepState },
        },
      }
    }),

  // chat actions
  setChats: (chats) => set({ chats }),

  prependChat: (chat) =>
    set((state) => ({ chats: [chat, ...state.chats] })),

  setActiveChatId: (id) => set({ activeChatId: id }),

  setMessages: (chatId, messages) =>
    set((state) => ({
      messages: { ...state.messages, [chatId]: messages },
    })),

  appendMessage: (chatId, msg) =>
    set((state) => ({
      messages: {
        ...state.messages,
        [chatId]: [...(state.messages[chatId] ?? []), msg],
      },
    })),

  setTrace: (traceId, trace) =>
    set((state) => ({
      traces: { ...state.traces, [traceId]: trace },
    })),

  // streaming actions
  startStream: (chatId) =>
    set({ streamingChatId: chatId, partialTokens: "", partialTrace: {} }),

  appendToken: (text) =>
    set((state) => ({ partialTokens: state.partialTokens + text })),

  mergeTracePartial: (data) =>
    set((state) => ({
      partialTrace: { ...state.partialTrace, ...data },
    })),

  finalizeStream: (msg, trace) =>
    set((state) => {
      const chatId = msg.chat_id
      const messages = {
        ...state.messages,
        [chatId]: [...(state.messages[chatId] ?? []), msg],
      }
      const traces = { ...state.traces, [trace.id]: trace }
      return {
        messages,
        traces,
        streamingChatId: null,
        partialTokens: "",
        partialTrace: {},
      }
    }),

  clearStream: () =>
    set({ streamingChatId: null, partialTokens: "", partialTrace: {} }),
}))
