"use client"

import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Badge } from "@/components/ui/badge"
import { useStore } from "@/lib/store"
import type { Message as MessageType } from "@/lib/types"

interface Props {
  message: MessageType
  /** When true, renders partialTokens from store with a blinking cursor */
  streaming?: boolean
  onCitationClick?: (hitIndex: number) => void
}

// Replace [N] tokens in text with clickable Badge elements
function parseContent(
  content: string,
  onCitationClick?: (index: number) => void
): React.ReactNode[] {
  const parts = content.split(/(\[\d+\])/g)
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/)
    if (match) {
      const n = parseInt(match[1], 10)
      return (
        <Badge
          key={i}
          variant="secondary"
          className="cursor-pointer text-xs px-1 py-0 mx-0.5 hover:bg-primary hover:text-primary-foreground"
          onClick={() => onCitationClick?.(n - 1)}
        >
          {n}
        </Badge>
      )
    }
    return part
  })
}

export default function Message({ message, streaming, onCitationClick }: Props) {
  const partialTokens = useStore((s) => s.partialTokens)
  const traces = useStore((s) => s.traces)

  const isUser = message.role === "user"
  const content = streaming ? partialTokens : message.content
  const isInterrupted = content.startsWith("[Generation interrupted]")

  const trace =
    message.trace_id && !streaming ? traces[message.trace_id] : null

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div
        className={`max-w-[75%] rounded-xl px-4 py-2.5 ${
          isUser
            ? "bg-muted text-foreground"
            : "bg-background border text-foreground"
        }`}
      >
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{content}</p>
        ) : (
          <div
            className={`prose prose-sm max-w-none dark:prose-invert ${
              isInterrupted ? "text-destructive" : ""
            }`}
          >
            {streaming ? (
              <p className="text-sm whitespace-pre-wrap">
                {content}
                <span className="inline-block w-0.5 h-3.5 bg-foreground ml-0.5 animate-pulse align-text-bottom" />
              </p>
            ) : (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p({ children }) {
                    // Intercept paragraphs to replace [N] with badges
                    const text =
                      typeof children === "string" ? children : String(children)
                    return (
                      <p className="mb-1 last:mb-0 text-sm">
                        {parseContent(text, onCitationClick)}
                      </p>
                    )
                  },
                }}
              >
                {content}
              </ReactMarkdown>
            )}
          </div>
        )}

        {/* Sources strip — only for completed assistant messages with a trace */}
        {!streaming && !isUser && trace && trace.semantic_hits.length > 0 && (
          <div className="mt-2 pt-2 border-t flex flex-wrap gap-1.5">
            {trace.semantic_hits.map((hit, i) => (
              <button
                key={hit.chunk_id}
                onClick={() => onCitationClick?.(i)}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                [{i + 1}] {hit.filename}
                {hit.source_page !== null ? ` · p.${hit.source_page}` : ""}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
