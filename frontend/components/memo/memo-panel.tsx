"use client";

import { useCallback, useRef, useState } from "react";
import {
  Bot,
  Loader2,
  ShieldCheck,
  ClipboardList,
  Files,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AgentReasoning } from "./agent-reasoning";
import { ScreeningPanel } from "@/components/case/screening-panel";
import { CDDChecklist } from "@/components/case/cdd-checklist";
import { DocumentList } from "@/components/case/document-list";
import { EscalateBanner } from "@/components/case/escalate-banner";
import { cn } from "@/lib/utils";
import type {
  AnalyzeResponse,
  UploadedDocumentMeta,
} from "@/types/edd";

interface MemoPanelProps {
  analysisResult: AnalyzeResponse | null;
  isLoading: boolean;
  documents: UploadedDocumentMeta[];
  onUploadFiles?: (files: File[]) => void;
  isUploading: boolean;
}

const ACCEPT = "application/pdf,.pdf";

function filterPdf(list: FileList | File[]): File[] {
  return Array.from(list).filter(
    (f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")
  );
}

export function MemoPanel({
  analysisResult,
  isLoading,
  documents,
  onUploadFiles,
  isUploading,
}: MemoPanelProps) {
  const [activeTab, setActiveTab] = useState<string>("checklist");
  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/10">
        <div className="text-center space-y-3">
          <Loader2 className="size-10 text-muted-foreground/40 mx-auto animate-spin" />
          <p className="text-sm text-muted-foreground">
            Building CDD checklist, resolving UBOs, screening watchlists…
          </p>
        </div>
      </div>
    );
  }

  if (!analysisResult) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/10">
        <div className="text-center space-y-2">
          <ClipboardList className="size-10 text-muted-foreground/30 mx-auto" />
          <p className="text-sm text-muted-foreground">
            Run the analysis to produce the CDD checklist and supporting outputs.
          </p>
        </div>
      </div>
    );
  }

  const label =
    analysisResult.applicant_name ||
    (analysisResult.fixture_id
      ? analysisResult.fixture_id.replace("fixture_", "Fixture ").toUpperCase()
      : "Case");

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-card/50">
        <div className="text-xs text-muted-foreground min-w-0">
          <span className="font-medium text-foreground truncate">{label}</span>
          <span className="ml-1">— {analysisResult.processing_ms}ms</span>
        </div>
      </div>

      {analysisResult.escalation?.escalated && (
        <EscalateBanner escalation={analysisResult.escalation} />
      )}

      <div className="flex-1 overflow-hidden">
        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="h-full flex flex-col"
        >
          <div className="px-3 pt-3 pb-0 border-b border-border">
            <TabsList className="h-8 w-full">
              <TabsTrigger value="checklist" className="flex-1 text-xs gap-1 px-2">
                <ClipboardList className="size-3 shrink-0" />
                <span className="truncate">CDD</span>
              </TabsTrigger>
              <TabsTrigger value="documents" className="flex-1 text-xs gap-1 px-2">
                <Files className="size-3 shrink-0" />
                <span className="truncate">
                  Docs{documents.length > 0 ? ` (${documents.length})` : ""}
                </span>
              </TabsTrigger>
              <TabsTrigger value="screening" className="flex-1 text-xs gap-1 px-2">
                <ShieldCheck className="size-3 shrink-0" />
                <span className="truncate">Screening</span>
              </TabsTrigger>
              <TabsTrigger value="reasoning" className="flex-1 text-xs gap-1 px-2">
                <Bot className="size-3 shrink-0" />
                <span className="truncate">Reasoning</span>
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="documents" className="flex-1 overflow-hidden mt-0">
            <ScrollArea className="h-full">
              <DocumentsTab
                documents={documents}
                onUploadFiles={onUploadFiles}
                isUploading={isUploading}
              />
            </ScrollArea>
          </TabsContent>

          <TabsContent value="screening" className="flex-1 overflow-hidden mt-0">
            <ScrollArea className="h-full">
              <ScreeningPanel ubos={analysisResult.resolved_ubos} />
            </ScrollArea>
          </TabsContent>

          <TabsContent value="checklist" className="flex-1 overflow-hidden mt-0">
            <ScrollArea className="h-full">
              <CDDChecklist checklist={analysisResult.cdd_checklist} />
            </ScrollArea>
          </TabsContent>

          <TabsContent value="reasoning" className="flex-1 overflow-hidden mt-0">
            <ScrollArea className="h-full">
              <div className="p-4" style={{ width: 0, minWidth: "100%", overflow: "hidden", boxSizing: "border-box" }}>
                <AgentReasoning
                  workProduct={analysisResult.agent_work_product}
                  agentTrace={analysisResult.agent_trace}
                  verifierReport={analysisResult.verifier_report}
                />
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

interface DocumentsTabProps {
  documents: UploadedDocumentMeta[];
  onUploadFiles?: (files: File[]) => void;
  isUploading: boolean;
}

function DocumentsTab({ documents, onUploadFiles, isUploading }: DocumentsTabProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const submit = useCallback(
    (raw: FileList | File[]) => {
      if (!onUploadFiles) return;
      const files = filterPdf(raw);
      if (files.length > 0) onUploadFiles(files);
    },
    [onUploadFiles]
  );

  return (
    <div className="p-3 space-y-3">
      {onUploadFiles && (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            if (!isUploading) setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            if (isUploading) return;
            if (e.dataTransfer.files?.length) submit(e.dataTransfer.files);
          }}
          className={cn(
            "flex items-center justify-between gap-3 rounded-lg border border-dashed px-3 py-2.5 transition-colors cursor-pointer",
            isDragging
              ? "border-primary bg-primary/5"
              : "border-border bg-muted/20 hover:bg-muted/40",
            isUploading && "opacity-60 cursor-not-allowed pointer-events-none"
          )}
          onClick={() => !isUploading && inputRef.current?.click()}
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
          <div className="flex items-center gap-2 min-w-0">
            {isUploading ? (
              <Loader2 className="size-4 text-primary animate-spin shrink-0" />
            ) : (
              <Upload className="size-4 text-muted-foreground shrink-0" />
            )}
            <div className="min-w-0">
              <p className="text-xs font-medium truncate">
                {isUploading ? "Uploading & classifying…" : "Add documents to this case"}
              </p>
              <p className="text-[10px] text-muted-foreground truncate">
                Drop PDFs here or click to browse
              </p>
            </div>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 text-xs gap-1 shrink-0"
            disabled={isUploading}
            onClick={(e) => {
              e.stopPropagation();
              inputRef.current?.click();
            }}
          >
            <Upload className="size-3" />
            Upload
          </Button>
        </div>
      )}

      <div className="rounded-lg border border-border overflow-hidden">
        <DocumentList documents={documents} />
      </div>
    </div>
  );
}
