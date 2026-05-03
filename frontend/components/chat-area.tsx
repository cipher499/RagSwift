"use client"

import { useEffect, useRef, useCallback } from "react"
import { SendIcon, Loader2Icon } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { api } from "@/lib/api"
import { streamMessage } from "@/lib/sse"
import { useStore } from "@/lib/store"
import type { Message as MessageType, Trace } from "@/lib/types"
import MessageBubble from "./message"

export default function ChatArea() {
  const activeChatId = useStore((s) => s.activeChatId)
  const messages = useStore((s) => s.messages)
  const documents = useStore((s) => s.documents)
  const streamingChatId = useStore((s) => s.streamingChatId)
  const traces = useStore((s) => s.traces)

  const setMessages = useStore((s) => s.setMessages)
  const appendMessage = useStore((s) => s.appendMessage)
  const setTrace = useStore((s) => s.setTrace)
  const startStream = useStore((s) => s.startStream)
  const appendToken = useStore((s) => s.appendToken)
  const mergeTracePartial = useStore((s) => s.mergeTracePartial)
  const finalizeStream = useStore((s) => s.finalizeStream)
  const clearStream = useStore((s) => s.clearStream)

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const chatMessages = activeChatId ? (messages[activeChatId] ?? null) : null
  const isStreaming = streamingChatId === activeChatId && activeChatId !== null
  const hasReady = documents.some((d) => d.status === "ready")

  // Load chat when activeChatId changes
  useEffect(() => {
    if (!activeChatId) return
    setMessages(activeChatId, []) // clear while loading — show skeletons
    api
      .getChat(activeChatId)
      .then(async ({ messages: msgs }) => {
        setMessages(activeChatId, msgs)
        // Load trace for last assistant message if it has one
        const last = [...msgs].reverse().find((m) => m.role === "assistant" && m.trace_id)
        if (last?.trace_id && !traces[last.trace_id]) {
          try {
            const trace = await api.getTrace(activeChatId, last.trace_id)
            setTrace(last.trace_id, trace)
          } catch {
            // non-critical
          }
        }
      })
      .catch((e) => toast.error(e.message))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChatId])

  // Scroll to bottom on new messages / tokens
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [chatMessages, isStreaming])

  const handleCitationClick = useCallback(
    (hitIndex: number) => {
      const el = document.getElementById(`hit-${hitIndex}`)
      el?.scrollIntoView({ behavior: "smooth", block: "center" })
    },
    []
  )

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const textarea = textareaRef.current
    if (!textarea || !activeChatId) return
    const content = textarea.value.trim()
    if (!content) return

    textarea.value = ""
    textarea.style.height = "auto"

    abortRef.current = new AbortController()
    startStream(activeChatId)

    let pendingMsg: MessageType | null = null
    let pendingTrace: Trace | null = null

    try {
      await streamMessage(
        activeChatId,
        content,
        {
          onUserSaved(d) {
            appendMessage(activeChatId, {
              id: d.message_id,
              chat_id: d.chat_id,
              role: "user",
              content,
              trace_id: null,
              created_at: new Date().toISOString(),
            })
          },
          onRewrite(d) {
            mergeTracePartial({ rewritten_query: d.rewritten_query })
          },
          onHits(d) {
            mergeTracePartial({ semantic_hits: d.semantic_hits })
          },
          onToken(d) {
            appendToken(d.text)
          },
          async onDone(d) {
            try {
              const trace = await api.getTrace(activeChatId, d.trace_id)
              pendingMsg = {
                id: d.message_id,
                chat_id: activeChatId,
                role: "assistant",
                content: useStore.getState().partialTokens,
                trace_id: d.trace_id,
                created_at: new Date().toISOString(),
              }
              pendingTrace = trace
              finalizeStream(pendingMsg, trace)
            } catch (e) {
              toast.error(`Failed to load trace: ${(e as Error).message}`)
              clearStream()
            }
          },
          onError(d) {
            clearStream()
            const detail = d instanceof Error ? d.message : d.detail
            toast.error(detail)
          },
        },
        abortRef.current.signal
      )
    } catch {
      // connection drop
      if (abortRef.current?.signal.aborted) return
      clearStream()
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault()
      handleSubmit(e as unknown as React.FormEvent)
    }
  }

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const el = e.target
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 144)}px` // ~6 rows
  }

  if (!activeChatId) return null

  const loading = chatMessages === null || chatMessages.length === 0 && !isStreaming && chatMessages !== undefined

  return (
    <div className="flex flex-col h-full">
      {/* Message list */}
      <div className="flex-1 overflow-auto px-4 py-4">
        {chatMessages === null ? (
          // Loading skeletons
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-12 w-3/4 rounded-xl" />
            ))}
          </div>
        ) : (
          <>
            {chatMessages.map((msg) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                onCitationClick={handleCitationClick}
              />
            ))}
            {/* Streaming bubble */}
            {isStreaming && (
              <MessageBubble
                message={{
                  id: "__streaming__",
                  chat_id: activeChatId,
                  role: "assistant",
                  content: "",
                  trace_id: null,
                  created_at: new Date().toISOString(),
                }}
                streaming
                onCitationClick={handleCitationClick}
              />
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t px-4 py-3">
        <form onSubmit={handleSubmit} className="flex gap-2 items-end">
          <Tooltip>
            <TooltipTrigger
              render={
                <div className="flex-1">
                  <Textarea
                    ref={textareaRef}
                    placeholder={
                      !hasReady
                        ? "Upload a document first"
                        : "Ask a question… (Ctrl+Enter to send)"
                    }
                    disabled={!hasReady || isStreaming}
                    onKeyDown={handleKeyDown}
                    onChange={handleInput}
                    rows={1}
                    className="resize-none overflow-hidden min-h-[40px] max-h-36"
                  />
                </div>
              }
            />
            {!hasReady && (
              <TooltipContent>Upload a document first</TooltipContent>
            )}
          </Tooltip>

          <Button
            type="submit"
            size="icon"
            disabled={!hasReady || isStreaming}
            className="shrink-0"
          >
            {isStreaming ? (
              <Loader2Icon className="h-4 w-4 animate-spin" />
            ) : (
              <SendIcon className="h-4 w-4" />
            )}
          </Button>
        </form>
        <p className="text-xs text-muted-foreground mt-1 text-right">
          Ctrl+Enter to send
        </p>
      </div>
    </div>
  )
}
