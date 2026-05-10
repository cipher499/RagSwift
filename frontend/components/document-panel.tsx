"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Upload, FileText, CheckCircle, XCircle, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/lib/store";
import { getDocuments, uploadDocument, API_URL } from "@/lib/api";
import type { Document, DocumentStatus, StepEvent, IngestionDoneEvent, IngestionErrorEvent } from "@/types";

const STEP_ORDER = ["upload", "parse", "chunk", "embed", "index"] as const;
type Step = typeof STEP_ORDER[number];

interface ProgressState {
  step: Step;
  state: "running" | "complete" | "failed";
  progress_pct: number;
  message: string | null;
}

function useIngestionProgress(documentId: string | null) {
  const upsertDocument = useAppStore((s) => s.upsertDocument);
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const ctrlRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!documentId) return;
    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;

    fetchEventSource(`${API_URL}/api/documents/${documentId}/progress`, {
      signal: ctrl.signal,
      onmessage(ev) {
        if (ev.event === "step") {
          const data = JSON.parse(ev.data) as StepEvent;
          setProgress({ step: data.step as Step, state: data.state, progress_pct: data.progress_pct, message: data.message });
        } else if (ev.event === "done") {
          const data = JSON.parse(ev.data) as IngestionDoneEvent;
          setProgress(null);
          // Refresh document
          getDocuments().then((docs) => {
            const updated = docs.find((d) => d.id === documentId);
            if (updated) upsertDocument(updated);
          });
          ctrl.abort();
        } else if (ev.event === "error") {
          const data = JSON.parse(ev.data) as IngestionErrorEvent;
          toast.error(`Ingestion failed: ${data.detail}`);
          setProgress(null);
          ctrl.abort();
        }
      },
      onerror(err) {
        if (!ctrl.signal.aborted) toast.error("Connection error during ingestion");
        throw err;
      },
    }).catch(() => {});

    return () => ctrl.abort();
  }, [documentId, upsertDocument]);

  return progress;
}

export function DocumentPanel() {
  const { documents, setDocuments, upsertDocument } = useAppStore();
  const loadedRef = useRef(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [activeIngestionId, setActiveIngestionId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    getDocuments()
      .then(setDocuments)
      .catch(() => toast.error("Failed to load documents"));
  }, [setDocuments]);

  const progress = useIngestionProgress(activeIngestionId);

  const handleFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      e.target.value = "";

      setUploading(true);
      try {
        const result = await uploadDocument(file);
        // Add pending document optimistically
        const pending: Document = {
          id: result.document_id,
          filename: result.filename,
          content_hash: "",
          mime_type: file.type,
          size_bytes: file.size,
          num_pages: null,
          num_chunks: 0,
          status: "pending",
          error_message: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        upsertDocument(pending);
        setActiveIngestionId(result.document_id);
        toast.success(`Uploading ${result.filename}…`);
      } catch (err: unknown) {
        toast.error(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setUploading(false);
      }
    },
    [upsertDocument]
  );

  return (
    <div className="w-64 shrink-0 hidden lg:flex flex-col h-full border-l bg-muted/20">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b">
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="flex items-center gap-1.5 text-sm font-semibold hover:text-foreground/80 transition-colors"
        >
          {collapsed ? <ChevronRight className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          Documents
        </button>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          title="Upload document"
          className="flex items-center justify-center size-8 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
        >
          {uploading ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.epub,.md,.txt"
          className="hidden"
          onChange={handleFileChange}
        />
      </div>

      {/* Document list */}
      {!collapsed && (
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {documents.length === 0 ? (
            <div className="px-2 py-8 flex flex-col items-center gap-2 text-center">
              <FileText className="size-8 text-muted-foreground/50" />
              <p className="text-xs text-muted-foreground">No documents yet</p>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="text-xs text-primary underline underline-offset-2"
              >
                Upload one
              </button>
            </div>
          ) : (
            documents.map((doc) => (
              <DocItem
                key={doc.id}
                doc={doc}
                progress={doc.id === activeIngestionId ? progress : null}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function DocItem({
  doc,
  progress,
}: {
  doc: Document;
  progress: ProgressState | null;
}) {
  return (
    <div className="rounded-md border bg-card p-2 text-xs space-y-1.5">
      <div className="flex items-start gap-1.5">
        <StatusIcon status={doc.status} className="mt-0.5 shrink-0" />
        <span className="flex-1 truncate font-medium" title={doc.filename}>
          {doc.filename}
        </span>
      </div>

      <div className="flex items-center justify-between text-muted-foreground">
        <span className="capitalize">{doc.status}</span>
        {doc.status === "ready" && (
          <span>{doc.num_chunks} chunks{doc.num_pages ? ` · ${doc.num_pages}p` : ""}</span>
        )}
      </div>

      {progress && (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="capitalize">{progress.step}ing…</span>
            <span>{progress.progress_pct}%</span>
          </div>
          <div className="h-1 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${progress.progress_pct}%` }}
            />
          </div>
          {progress.message && <p className="text-muted-foreground truncate">{progress.message}</p>}
        </div>
      )}

      {doc.error_message && (
        <p className="text-destructive truncate" title={doc.error_message}>
          {doc.error_message}
        </p>
      )}
    </div>
  );
}

function StatusIcon({ status, className }: { status: DocumentStatus; className?: string }) {
  if (status === "ready") return <CheckCircle className={cn("size-3.5 text-green-500", className)} />;
  if (status === "failed") return <XCircle className={cn("size-3.5 text-destructive", className)} />;
  if (status === "pending") return <div className={cn("size-3.5 rounded-full bg-muted-foreground/30", className)} />;
  return <Loader2 className={cn("size-3.5 animate-spin text-primary", className)} />;
}
