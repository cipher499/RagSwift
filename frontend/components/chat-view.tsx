"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Send, Loader2, Bot, User, FlaskConical } from "lucide-react";
import { toast } from "sonner";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/lib/store";
import { getChat, getTrace, API_URL } from "@/lib/api";
import type { Message, TracePartial } from "@/types";
import { TracePanel } from "./trace-panel";

// Sentinel ID used for the optimistic assistant message while streaming
const STREAMING_ID = "__streaming__";

class FatalError extends Error {}

export function ChatView() {
  const {
    activeChatId,
    messages,
    setMessages,
    addMessage,
    updateMessage,
    setTrace,
    openTrace,
    traces,
    activeTraceId,
    activeTraceChatId,
    closeTrace,
  } = useAppStore();

  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const ctrlRef = useRef<AbortController | null>(null);
  const loadedChatRef = useRef<string | null>(null);

  // Load messages when active chat changes
  useEffect(() => {
    if (!activeChatId) return;
    if (loadedChatRef.current === activeChatId) return;
    loadedChatRef.current = activeChatId;

    if (!messages[activeChatId]) {
      getChat(activeChatId)
        .then(({ messages: msgs }) => setMessages(activeChatId, msgs))
        .catch(() => toast.error("Failed to load messages"));
    }
  }, [activeChatId, messages, setMessages]);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeChatId, streamingContent]);

  const handleSend = useCallback(async () => {
    const content = input.trim();
    if (!content || !activeChatId || isStreaming) return;

    setInput("");
    setIsStreaming(true);
    setStreamingContent("");

    // Optimistic user message
    const tempUserId = `temp-user-${Date.now()}`;
    addMessage(activeChatId, {
      id: tempUserId,
      chat_id: activeChatId,
      role: "user",
      content,
      trace_id: null,
      created_at: new Date().toISOString(),
    });

    // Optimistic assistant placeholder
    addMessage(activeChatId, {
      id: STREAMING_ID,
      chat_id: activeChatId,
      role: "assistant",
      content: "",
      trace_id: null,
      created_at: new Date().toISOString(),
    });

    let accumulated = "";
    let tracePartial: TracePartial = {};
    let finalMsgId = STREAMING_ID;
    let finalTraceId: string | null = null;

    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;

    try {
      await fetchEventSource(`${API_URL}/api/chats/${activeChatId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
        signal: ctrl.signal,
        async onopen(res) {
          if (res.ok && res.headers.get("content-type")?.includes("text/event-stream")) return;
          if (res.status >= 400 && res.status < 500 && res.status !== 429) {
            const body = await res.json().catch(() => ({}));
            throw new FatalError(body?.detail ?? `HTTP ${res.status}`);
          }
          throw new Error("Unexpected response");
        },
        onmessage(ev) {
          if (!ev.data) return;
          const data = JSON.parse(ev.data);

          if (ev.event === "user_message_saved") {
            updateMessage(activeChatId, tempUserId, { id: data.message_id });
          } else if (ev.event === "trace_partial") {
            tracePartial = { ...tracePartial, ...data };
          } else if (ev.event === "token") {
            accumulated += data.text;
            setStreamingContent(accumulated);
          } else if (ev.event === "done") {
            finalMsgId = data.message_id;
            finalTraceId = data.trace_id ?? null;
            ctrl.abort();
          } else if (ev.event === "error") {
            throw new FatalError(data.detail ?? data.error);
          }
        },
        onerror(err) {
          if (err instanceof FatalError) throw err;
        },
      });
    } catch (err: unknown) {
      if (!ctrl.signal.aborted) {
        toast.error(err instanceof Error ? err.message : "Something went wrong");
      }
    }

    // Finalize assistant message
    updateMessage(activeChatId, STREAMING_ID, {
      id: finalMsgId,
      content: accumulated,
      trace_id: finalTraceId,
    });

    setStreamingContent("");
    setIsStreaming(false);
  }, [input, activeChatId, isStreaming, addMessage, updateMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleViewTrace = useCallback(
    async (msg: Message) => {
      if (!msg.trace_id || !activeChatId) return;
      // Use cached trace or fetch
      if (!traces[msg.trace_id]) {
        try {
          const trace = await getTrace(activeChatId, msg.trace_id);
          setTrace(msg.trace_id, trace);
        } catch {
          toast.error("Failed to load trace");
          return;
        }
      }
      openTrace(msg.trace_id, activeChatId);
    },
    [activeChatId, traces, setTrace, openTrace]
  );

  // No chat selected
  if (!activeChatId) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center px-8">
        <Bot className="size-10 text-muted-foreground/40" />
        <p className="text-sm text-muted-foreground">
          Select a chat or create a new one to get started.
        </p>
      </div>
    );
  }

  const chatMessages = (messages[activeChatId] ?? []).filter((m) => m.id !== STREAMING_ID);
  const showStreaming = isStreaming;

  return (
    <div className="flex flex-1 flex-col min-w-0 h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-6 space-y-4">
          {chatMessages.length === 0 && !showStreaming && (
            <div className="flex flex-col items-center gap-3 py-16 text-center">
              <Bot className="size-8 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">
                Ask a question about your uploaded documents.
              </p>
            </div>
          )}

          {chatMessages.map((msg) => (
            <MessageItem
              key={msg.id}
              msg={msg}
              onViewTrace={msg.role === "assistant" && msg.trace_id ? () => handleViewTrace(msg) : undefined}
            />
          ))}

          {showStreaming && (
            <MessageItem
              msg={{
                id: STREAMING_ID,
                chat_id: activeChatId,
                role: "assistant",
                content: streamingContent,
                trace_id: null,
                created_at: new Date().toISOString(),
              }}
              streaming
            />
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t bg-background px-4 py-3">
        <div className="mx-auto max-w-3xl flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your documents…"
            rows={1}
            disabled={isStreaming}
            className={cn(
              "flex-1 resize-none rounded-lg border bg-input px-3 py-2 text-sm",
              "placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring",
              "min-h-[40px] max-h-[160px] disabled:opacity-50"
            )}
            style={{ height: "auto" }}
            onInput={(e) => {
              const t = e.currentTarget;
              t.style.height = "auto";
              t.style.height = `${Math.min(t.scrollHeight, 160)}px`;
            }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
            className={cn(
              "flex items-center justify-center size-10 rounded-lg",
              "bg-primary text-primary-foreground",
              "hover:bg-primary/90 transition-colors",
              "disabled:opacity-50 disabled:pointer-events-none shrink-0"
            )}
          >
            {isStreaming ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          </button>
        </div>
      </div>

      {/* Trace panel */}
      {activeTraceId && activeTraceChatId && (
        <TracePanel
          traceId={activeTraceId}
          chatId={activeTraceChatId}
          onClose={closeTrace}
        />
      )}
    </div>
  );
}

function MessageItem({
  msg,
  streaming,
  onViewTrace,
}: {
  msg: Message;
  streaming?: boolean;
  onViewTrace?: () => void;
}) {
  const isUser = msg.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="flex items-start gap-2 max-w-[80%]">
          <div className="rounded-2xl rounded-tr-sm bg-primary px-4 py-2 text-sm text-primary-foreground">
            {msg.content}
          </div>
          <div className="flex items-center justify-center size-7 rounded-full bg-muted shrink-0 mt-0.5">
            <User className="size-3.5 text-muted-foreground" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2">
      <div className="flex items-center justify-center size-7 rounded-full bg-primary shrink-0 mt-0.5">
        <Bot className="size-3.5 text-primary-foreground" />
      </div>
      <div className="flex-1 min-w-0 space-y-1">
        <div
          className={cn(
            "rounded-2xl rounded-tl-sm bg-muted/50 border px-4 py-3 text-sm",
            "prose prose-sm max-w-none dark:prose-invert"
          )}
        >
          {msg.content || streaming ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
          ) : null}
          {streaming && !msg.content && (
            <span className="inline-flex items-center gap-1 text-muted-foreground text-xs">
              <Loader2 className="size-3 animate-spin" /> Thinking…
            </span>
          )}
        </div>
        {onViewTrace && (
          <button
            onClick={onViewTrace}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors px-1"
          >
            <FlaskConical className="size-3" />
            View retrieval
          </button>
        )}
      </div>
    </div>
  );
}
