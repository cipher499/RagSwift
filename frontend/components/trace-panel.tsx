"use client";

import { useEffect } from "react";
import { X, Search, Sparkles, AlertTriangle, Clock } from "lucide-react";
import { toast } from "sonner";
import { useAppStore } from "@/lib/store";
import { getTrace } from "@/lib/api";
import type { Hit } from "@/types";
import { cn } from "@/lib/utils";

export function TracePanel({
  traceId,
  chatId,
  onClose,
}: {
  traceId: string;
  chatId: string;
  onClose: () => void;
}) {
  const { traces, setTrace } = useAppStore();
  const trace = traces[traceId];

  useEffect(() => {
    if (trace) return;
    getTrace(chatId, traceId)
      .then((t) => setTrace(traceId, t))
      .catch(() => toast.error("Failed to load trace"));
  }, [trace, traceId, chatId, setTrace]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const activeFlags = trace ? Object.entries(trace.flags).filter(([, v]) => v) : [];

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/20"
        onClick={onClose}
        aria-hidden
      />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-background shadow-xl border-l">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-4 py-3 shrink-0">
          <div className="flex items-center gap-2">
            <Search className="size-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Retrieval Trace</h2>
          </div>
          <button
            onClick={onClose}
            className="flex items-center justify-center size-7 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          {!trace ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <>
              {/* Queries */}
              <section className="space-y-2">
                <h3 className="text-xs font-medium uppercase text-muted-foreground tracking-wide">Query</h3>
                <div className="space-y-1.5">
                  <div className="rounded-md bg-muted/50 border px-3 py-2 text-sm">
                    <span className="text-xs text-muted-foreground block mb-0.5">Original</span>
                    {trace.original_query}
                  </div>
                  {trace.rewritten_query && trace.rewritten_query !== trace.original_query && (
                    <div className="rounded-md bg-muted/50 border px-3 py-2 text-sm">
                      <span className="text-xs text-muted-foreground flex items-center gap-1 mb-0.5">
                        <Sparkles className="size-3" /> Rewritten
                      </span>
                      {trace.rewritten_query}
                    </div>
                  )}
                </div>
              </section>

              {/* Semantic hits */}
              <section className="space-y-2">
                <h3 className="text-xs font-medium uppercase text-muted-foreground tracking-wide">
                  Semantic Hits ({trace.semantic_hits.length})
                </h3>
                {trace.semantic_hits.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No hits</p>
                ) : (
                  <div className="space-y-2">
                    {trace.semantic_hits.map((hit) => (
                      <HitCard key={hit.chunk_id} hit={hit} />
                    ))}
                  </div>
                )}
              </section>

              {/* Flags */}
              {activeFlags.length > 0 && (
                <section className="space-y-2">
                  <h3 className="text-xs font-medium uppercase text-muted-foreground tracking-wide">Flags</h3>
                  <div className="flex flex-wrap gap-1.5">
                    {activeFlags.map(([flag]) => (
                      <span
                        key={flag}
                        className="inline-flex items-center gap-1 rounded-full border bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-400"
                      >
                        <AlertTriangle className="size-3" />
                        {flag.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                </section>
              )}

              {/* Meta */}
              <section className="flex items-center gap-4 text-xs text-muted-foreground border-t pt-3">
                <span className="flex items-center gap-1">
                  <Clock className="size-3" />
                  {trace.latency_ms} ms
                </span>
                {trace.langsmith_run_url && (
                  <a
                    href={trace.langsmith_run_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline underline-offset-2 hover:text-foreground"
                  >
                    LangSmith
                  </a>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </>
  );
}

function HitCard({ hit }: { hit: Hit }) {
  return (
    <div className="rounded-md border bg-card p-3 text-xs space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium truncate" title={hit.filename}>
          {hit.filename}
          {hit.source_page != null && (
            <span className="text-muted-foreground ml-1">p.{hit.source_page}</span>
          )}
        </span>
        <span
          className={cn(
            "shrink-0 tabular-nums font-mono",
            hit.score >= 0.8
              ? "text-green-600 dark:text-green-400"
              : hit.score >= 0.5
              ? "text-amber-600 dark:text-amber-400"
              : "text-muted-foreground"
          )}
        >
          {hit.score.toFixed(3)}
        </span>
      </div>
      <p className="text-muted-foreground line-clamp-3 leading-relaxed">{hit.text}</p>
    </div>
  );
}
