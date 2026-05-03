"use client"

import { useEffect, useState } from "react"
import { CheckIcon, XIcon, Loader2Icon } from "lucide-react"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useStore } from "@/lib/store"
import type { Document, IngestionStep, StepState } from "@/lib/types"

const STEPS: IngestionStep[] = ["upload", "parse", "chunk", "embed", "index"]

interface Props {
  doc: Document
}

function StepPill({
  step,
  state,
  errorMessage,
}: {
  step: IngestionStep
  state: StepState
  errorMessage?: string | null
}) {
  const base = "flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium border transition-colors"

  const styles: Record<StepState, string> = {
    pending: "border-border bg-background text-muted-foreground",
    running: "border-blue-400 bg-blue-500 text-white",
    complete: "border-green-500 bg-green-500 text-white",
    failed: "border-red-500 bg-red-500 text-white",
  }

  const pill = (
    <span className={`${base} ${styles[state]}`}>
      {state === "running" && <Loader2Icon className="h-3 w-3 animate-spin" />}
      {state === "complete" && <CheckIcon className="h-3 w-3" />}
      {state === "failed" && <XIcon className="h-3 w-3" />}
      {step}
    </span>
  )

  if (state === "failed" && errorMessage) {
    return (
      <Tooltip>
        <TooltipTrigger render={pill} />
        <TooltipContent>{errorMessage}</TooltipContent>
      </Tooltip>
    )
  }

  return pill
}

export default function IngestionCard({ doc }: Props) {
  const steps = useStore((s) => s.ingestionSteps[doc.id])
  const [collapsed, setCollapsed] = useState(false)

  // Collapse to summary row 1.5 s after done
  useEffect(() => {
    if (doc.status === "ready") {
      const t = setTimeout(() => setCollapsed(true), 1500)
      return () => clearTimeout(t)
    }
  }, [doc.status])

  // Never auto-hide errors
  if (doc.status === "failed" || collapsed) {
    return (
      <div className="flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm">
        {doc.status === "ready" ? (
          <>
            <CheckIcon className="h-4 w-4 text-green-500 shrink-0" />
            <span className="truncate font-medium">{doc.filename}</span>
            <span className="text-muted-foreground shrink-0">
              · {doc.num_chunks} chunks
            </span>
          </>
        ) : (
          <>
            <XIcon className="h-4 w-4 text-red-500 shrink-0" />
            <span className="truncate font-medium text-destructive">{doc.filename}</span>
            {doc.error_message && (
              <span className="text-xs text-muted-foreground shrink-0 truncate max-w-[160px]">
                {doc.error_message}
              </span>
            )}
          </>
        )}
      </div>
    )
  }

  return (
    <div className="rounded-md border bg-card px-3 py-2 space-y-2">
      <p className="text-sm font-medium truncate">{doc.filename}</p>
      <div className="flex flex-wrap gap-1.5">
        {STEPS.map((step) => (
          <StepPill
            key={step}
            step={step}
            state={steps?.[step] ?? "pending"}
            errorMessage={doc.error_message}
          />
        ))}
      </div>
    </div>
  )
}
