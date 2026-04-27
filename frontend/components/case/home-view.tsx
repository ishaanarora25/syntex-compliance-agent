"use client";

import { useCallback, useRef, useState } from "react";
import {
  FileUp,
  FileText,
  X,
  Loader2,
  Sparkles,
  Play,
  FlaskConical,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { CaseDetail, FixtureMeta } from "@/types/edd";

interface HomeViewProps {
  pendingFiles: File[];
  selectedCase: CaseDetail | null;
  selectedFixture: FixtureMeta | null;
  isUploading: boolean;
  isAnalyzing: boolean;
  onAddFiles: (files: File[]) => void;
  onRemovePendingFile: (index: number) => void;
  onAnalyze: () => void;
}

const ACCEPT = "application/pdf,.pdf";

function filterPdf(list: FileList | File[]): File[] {
  return Array.from(list).filter(
    (f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")
  );
}

function prettyBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function HomeView({
  pendingFiles,
  selectedCase,
  selectedFixture,
  isUploading,
  isAnalyzing,
  onAddFiles,
  onRemovePendingFile,
  onAnalyze,
}: HomeViewProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const submit = useCallback(
    (raw: FileList | File[]) => {
      const files = filterPdf(raw);
      if (files.length > 0) onAddFiles(files);
    },
    [onAddFiles]
  );

  const busy = isUploading || isAnalyzing;

  // Determine what to show in the context strip below the logo
  const contextLabel = selectedFixture
    ? selectedFixture.label
    : selectedCase
    ? selectedCase.name
    : null;

  // Files to display (pending or uploaded to selected case)
  const caseDocs = selectedCase?.documents ?? [];
  const showPending = !selectedCase && pendingFiles.length > 0;
  const showCaseDocs = !!selectedCase && caseDocs.length > 0;
  const hasFiles = showPending || showCaseDocs;

  const canRun =
    !busy &&
    (selectedFixture != null ||
      (selectedCase != null && caseDocs.length > 0) ||
      pendingFiles.length > 0);

  return (
    <div className="flex flex-col flex-1 min-h-0 overflow-y-auto">
      <div className="flex flex-col items-center justify-center flex-1 px-6 py-16 min-h-[480px]">
        <div className="w-full max-w-2xl flex flex-col gap-6">

          {/* Heading */}
          <div className="text-center">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">
              {contextLabel
                ? contextLabel
                : "Start with your formation documents"}
            </h1>
            <p className="mt-1.5 text-sm text-muted-foreground">
              {selectedFixture
                ? `Demo scenario · ${selectedFixture.scenario} — ${selectedFixture.description}`
                : selectedCase
                ? `${caseDocs.length} document${caseDocs.length !== 1 ? "s" : ""} uploaded · drop more below to add`
                : "Syntex resolves beneficial ownership, screens OFAC / PEP / adverse media, and drafts your EDD memo."}
            </p>
          </div>

          {/* Drop zone — hidden for fixture mode */}
          {!selectedFixture && (
            <div
              onDragOver={(e) => {
                e.preventDefault();
                if (!busy) setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragging(false);
                if (busy) return;
                if (e.dataTransfer.files?.length) submit(e.dataTransfer.files);
              }}
              className={cn(
                "relative flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-8 py-12 transition-all cursor-pointer",
                isDragging
                  ? "border-primary bg-primary/5 scale-[1.01]"
                  : "border-border bg-muted/20 hover:bg-muted/40 hover:border-muted-foreground/40",
                busy && "opacity-60 cursor-not-allowed pointer-events-none"
              )}
              onClick={() => !busy && inputRef.current?.click()}
            >
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPT}
                multiple
                className="hidden"
                onChange={(e) => {
                  if (e.target.files?.length) submit(e.target.files);
                  e.target.value = "";
                }}
              />

              {isUploading ? (
                <>
                  <Loader2 className="size-8 text-primary animate-spin" />
                  <p className="text-sm font-medium">Extracting & classifying…</p>
                  <p className="text-xs text-muted-foreground text-center">
                    Reading PDFs, identifying entities, building the ownership
                    graph.
                  </p>
                </>
              ) : (
                <>
                  <div className="flex size-14 items-center justify-center rounded-2xl bg-muted border border-border">
                    <FileUp className="size-6 text-muted-foreground" />
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-medium text-foreground">
                      Drop formation &amp; KYC documents here
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground max-w-sm">
                      Articles of org, operating agreements, trust agreements,
                      LP agreements, commercial register extracts, IDs
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="gap-1.5 pointer-events-auto"
                    onClick={(e) => {
                      e.stopPropagation();
                      inputRef.current?.click();
                    }}
                  >
                    <FileText className="size-3.5" />
                    Browse files
                  </Button>
                </>
              )}
            </div>
          )}

          {/* Fixture placeholder */}
          {selectedFixture && (
            <div className="flex items-center gap-3 rounded-2xl border border-border bg-muted/20 px-5 py-5">
              <div className="flex size-10 items-center justify-center rounded-xl bg-muted border border-border shrink-0">
                <FlaskConical className="size-5 text-muted-foreground" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">Pre-loaded demo fixture</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Press <span className="font-medium">Run Analysis</span> to
                  resolve UBOs, screen watchlists, and draft the memo.
                </p>
              </div>
            </div>
          )}

          {/* Queued or uploaded file list */}
          {hasFiles && (
            <div className="rounded-xl border border-border bg-card overflow-hidden">
              <div className="px-4 py-2 border-b border-border bg-muted/30 flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {showPending ? "Queued for upload" : "Uploaded documents"}
                </span>
                <span className="text-xs text-muted-foreground">
                  {showPending ? pendingFiles.length : caseDocs.length} file
                  {(showPending ? pendingFiles.length : caseDocs.length) !== 1
                    ? "s"
                    : ""}
                </span>
              </div>
              <ul className="divide-y divide-border">
                {showPending &&
                  pendingFiles.map((f, i) => (
                    <li
                      key={`${f.name}-${i}`}
                      className="flex items-center gap-3 px-4 py-2.5"
                    >
                      <FileText className="size-4 text-muted-foreground shrink-0" />
                      <span className="flex-1 min-w-0 text-sm truncate">
                        {f.name}
                      </span>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {prettyBytes(f.size)}
                      </span>
                      <button
                        onClick={() => onRemovePendingFile(i)}
                        className="text-muted-foreground hover:text-foreground transition-colors shrink-0"
                        aria-label="Remove"
                      >
                        <X className="size-3.5" />
                      </button>
                    </li>
                  ))}
                {showCaseDocs &&
                  caseDocs.map((d) => (
                    <li
                      key={d.doc_id}
                      className="flex items-center gap-3 px-4 py-2.5"
                    >
                      <FileText className="size-4 text-muted-foreground shrink-0" />
                      <span className="flex-1 min-w-0 text-sm truncate">
                        {d.label || d.filename}
                      </span>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {d.page_count}p
                      </span>
                    </li>
                  ))}
              </ul>
            </div>
          )}

          {/* Run Analysis button */}
          <div className="flex justify-center">
            <Button
              size="lg"
              onClick={onAnalyze}
              disabled={!canRun}
              className="gap-2 px-8 text-base h-12 rounded-xl shadow-sm"
            >
              {isAnalyzing ? (
                <>
                  <Loader2 className="size-5 animate-spin" />
                  Running analysis…
                </>
              ) : selectedFixture ? (
                <>
                  <Play className="size-4" />
                  Run Analysis
                </>
              ) : (
                <>
                  <Sparkles className="size-4" />
                  Run Analysis
                </>
              )}
            </Button>
          </div>

          {!canRun && !busy && (
            <p className="text-center text-xs text-muted-foreground -mt-2">
              {selectedFixture
                ? null
                : "Upload at least one document to continue"}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
