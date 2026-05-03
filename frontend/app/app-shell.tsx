"use client"

import { PanelRightIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useStore } from "@/lib/store"

// Wraps the trace panel: hidden until first assistant message, collapsible toggle
export default function AppShell({ children }: { children: React.ReactNode }) {
  const traces = useStore((s) => s.traces)
  const partialTrace = useStore((s) => s.partialTrace)
  const streamingChatId = useStore((s) => s.streamingChatId)

  // Show once any trace data exists (streaming partial or persisted)
  const hasTraceData =
    Object.keys(traces).length > 0 ||
    streamingChatId !== null ||
    Object.keys(partialTrace).length > 0

  if (!hasTraceData) return null

  return (
    <div className="w-80 shrink-0 border-l flex flex-col h-full overflow-auto">
      {children}
    </div>
  )
}

// Standalone toggle button for the top-right of the main area (used by chat-area)
export function TracePanelToggle() {
  const traces = useStore((s) => s.traces)
  const streamingChatId = useStore((s) => s.streamingChatId)
  const hasTraceData = Object.keys(traces).length > 0 || streamingChatId !== null

  if (!hasTraceData) return null

  return (
    <Button size="icon" variant="ghost" title="Toggle trace panel">
      <PanelRightIcon className="h-4 w-4" />
    </Button>
  )
}
