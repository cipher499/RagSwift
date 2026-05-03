"use client"

import { useCallback, useRef } from "react"
import { UploadCloudIcon, ArrowRightIcon } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import { subscribeIngestionProgress } from "@/lib/sse"
import { useStore } from "@/lib/store"
import IngestionCard from "./ingestion-card"

const ACCEPTED = ".pdf,.epub,.docx,.md,.txt"

export default function UploadPanel() {
  const documents = useStore((s) => s.documents)
  const upsertDocument = useStore((s) => s.upsertDocument)
  const setStepState = useStore((s) => s.setStepState)
  const prependChat = useStore((s) => s.prependChat)
  const setActiveChatId = useStore((s) => s.setActiveChatId)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const hasReady = documents.some((d) => d.status === "ready")

  async function handleNewChat() {
    try {
      const chat = await api.createChat()
      prependChat(chat)
      setActiveChatId(chat.id)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  const processFiles = useCallback(
    async (files: FileList | File[]) => {
      const arr = Array.from(files)
      for (const file of arr) {
        let docId: string
        try {
          const res = await api.uploadDocument(file)
          docId = res.document_id
          upsertDocument({
            id: docId,
            filename: res.filename,
            status: "pending",
            content_hash: "",
            mime_type: file.type,
            size_bytes: file.size,
            num_pages: null,
            num_chunks: 0,
            error_message: null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          })
        } catch (e) {
          toast.error(`Upload failed: ${(e as Error).message}`)
          continue
        }

        const controller = new AbortController()
        subscribeIngestionProgress(
          docId,
          {
            onStep(d) {
              setStepState(docId, d.step, d.state)
            },
            onDone(d) {
              upsertDocument({
                id: docId,
                filename: file.name,
                status: "ready",
                content_hash: "",
                mime_type: file.type,
                size_bytes: file.size,
                num_pages: d.num_pages,
                num_chunks: d.num_chunks,
                error_message: null,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              })
            },
            onError(d) {
              setStepState(docId, d.step, "failed")
              upsertDocument({
                id: docId,
                filename: file.name,
                status: "failed",
                content_hash: "",
                mime_type: file.type,
                size_bytes: file.size,
                num_pages: null,
                num_chunks: 0,
                error_message: d.detail,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              })
              toast.error(`Ingestion failed: ${d.detail}`)
            },
          },
          controller.signal
        ).catch(() => {/* connection errors handled via onError */})
      }
    },
    [upsertDocument, setStepState]
  )

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    processFiles(e.dataTransfer.files)
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) processFiles(e.target.files)
  }

  const inProgressDocs = documents.filter(
    (d) => d.status !== "ready" || true // show all so cards can collapse themselves
  )

  return (
    <div className="flex flex-col h-full p-6 gap-4 overflow-auto">
      {/* Drag-drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => fileInputRef.current?.click()}
        className="flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-border bg-muted/20 p-12 cursor-pointer hover:bg-muted/40 transition-colors"
      >
        <UploadCloudIcon className="h-10 w-10 text-muted-foreground" />
        <div className="text-center">
          <p className="font-medium">Drop files here or click to browse</p>
          <p className="text-sm text-muted-foreground mt-1">
            PDF, EPUB, DOCX, Markdown, TXT · max 50 MB
          </p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED}
          multiple
          className="hidden"
          onChange={handleFileChange}
        />
      </div>

      {/* Ingestion cards */}
      {inProgressDocs.length > 0 && (
        <div className="space-y-2">
          {inProgressDocs.map((doc) => (
            <IngestionCard key={doc.id} doc={doc} />
          ))}
        </div>
      )}

      {/* Ready banner */}
      {hasReady && (
        <div className="flex items-center justify-between rounded-lg border border-green-200 bg-green-50 px-4 py-3">
          <p className="text-sm font-medium text-green-800">
            Ready to chat. Ask a question →
          </p>
          <Button
            size="sm"
            variant="default"
            onClick={handleNewChat}
            className="gap-1"
          >
            New chat <ArrowRightIcon className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
    </div>
  )
}
