"use client"

import { ExternalLinkIcon, ChevronDownIcon } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible"
import { useStore } from "@/lib/store"

function SectionHeader({ title }: { title: string }) {
  return (
    <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:bg-muted/50 transition-colors">
      {title}
      <ChevronDownIcon className="h-3.5 w-3.5 transition-transform group-data-[open]:rotate-180" />
    </CollapsibleTrigger>
  )
}

export default function TracePanel() {
  const partialTrace = useStore((s) => s.partialTrace)
  const streamingChatId = useStore((s) => s.streamingChatId)
  const traces = useStore((s) => s.traces)
  const activeChatId = useStore((s) => s.activeChatId)
  const messages = useStore((s) => s.messages)

  // During stream: use partialTrace; after done: use last trace for active chat
  let trace = partialTrace
  if (!streamingChatId && activeChatId) {
    const msgs = messages[activeChatId] ?? []
    const last = [...msgs].reverse().find((m) => m.role === "assistant" && m.trace_id)
    if (last?.trace_id && traces[last.trace_id]) {
      trace = traces[last.trace_id]
    }
  }

  const rewrittenQuery = trace.rewritten_query ?? null
  const semanticHits = trace.semantic_hits ?? []
  const flags = (trace as { flags?: Record<string, boolean> }).flags ?? {}
  const latencyMs = (trace as { latency_ms?: number }).latency_ms ?? null
  const langsmithUrl = (trace as { langsmith_run_url?: string | null }).langsmith_run_url ?? null

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b">
        <h2 className="text-sm font-semibold">Retrieval Trace</h2>
      </div>

      <div className="flex-1 overflow-auto divide-y">
        {/* Section 1: Rewrite */}
        <Collapsible defaultOpen className="group">
          <SectionHeader title="Query Rewrite" />
          <CollapsibleContent className="px-3 pb-3 space-y-1.5">
            {flags.rewrite_fallback && (
              <Badge variant="outline" className="border-yellow-400 text-yellow-700 bg-yellow-50 text-xs">
                ⚠ rewrite fallback — original query used
              </Badge>
            )}
            {rewrittenQuery ? (
              <p className="text-sm">{rewrittenQuery}</p>
            ) : (
              <p className="text-xs text-muted-foreground italic">Waiting…</p>
            )}
          </CollapsibleContent>
        </Collapsible>

        {/* Section 2: Semantic Hits */}
        <Collapsible defaultOpen className="group">
          <SectionHeader title="Semantic Hits" />
          <CollapsibleContent className="px-3 pb-3">
            {flags.semantic_fallback && (
              <Badge variant="outline" className="border-yellow-400 text-yellow-700 bg-yellow-50 text-xs mb-2">
                ⚠ semantic fallback
              </Badge>
            )}
            {semanticHits.length === 0 ? (
              <p className="text-xs text-muted-foreground italic">No hits retrieved</p>
            ) : (
              <div className="space-y-2">
                {semanticHits.map((hit, i) => (
                  <div
                    key={hit.chunk_id}
                    id={`hit-${i}`}
                    className="rounded border bg-muted/20 p-2 text-xs scroll-mt-2"
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="font-medium text-muted-foreground">
                        #{i + 1} · {hit.filename}
                        {hit.source_page !== null ? ` · p.${hit.source_page}` : ""}
                      </span>
                      <Badge variant="secondary" className="text-[10px] px-1 py-0 shrink-0">
                        {hit.score.toFixed(2)}
                      </Badge>
                    </div>
                    <details>
                      <summary className="cursor-pointer text-muted-foreground line-clamp-2">
                        {hit.text.slice(0, 120)}
                        {hit.text.length > 120 ? "…" : ""}
                      </summary>
                      <p className="mt-1 whitespace-pre-wrap">{hit.text}</p>
                    </details>
                  </div>
                ))}
              </div>
            )}
          </CollapsibleContent>
        </Collapsible>

        {/* Section 3: Flags */}
        <Collapsible defaultOpen className="group">
          <SectionHeader title="Flags" />
          <CollapsibleContent className="px-3 pb-3">
            {Object.keys(flags).length === 0 ? (
              <p className="text-xs text-muted-foreground italic">No flags</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(flags).map(([key, val]) => (
                  <Badge
                    key={key}
                    variant="outline"
                    className={
                      val
                        ? "border-yellow-400 text-yellow-700 bg-yellow-50 text-xs"
                        : "border-border text-muted-foreground text-xs"
                    }
                  >
                    {key}
                  </Badge>
                ))}
              </div>
            )}
          </CollapsibleContent>
        </Collapsible>

        {/* Section 4: Meta */}
        <Collapsible defaultOpen className="group">
          <SectionHeader title="Meta" />
          <CollapsibleContent className="px-3 pb-3 space-y-1.5 text-xs text-muted-foreground">
            {latencyMs !== null ? (
              <p>Latency: {latencyMs} ms</p>
            ) : (
              <p className="italic">Latency: —</p>
            )}
            {langsmithUrl && (
              <a
                href={langsmithUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-blue-600 hover:underline"
              >
                LangSmith trace <ExternalLinkIcon className="h-3 w-3" />
              </a>
            )}
          </CollapsibleContent>
        </Collapsible>
      </div>
    </div>
  )
}
