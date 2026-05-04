"use client";

import { Loader2, Play, CircleDashed, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { DocumentUpload } from "./document-upload";
import { DocumentList } from "./document-list";
import { LiveAgentPanel } from "./live-agent-panel";
import type { LiveAgentEvent, LiveAgentStage } from "@/components/scenario/use-scenario";
import type { CaseDetail, FixtureMeta } from "@/types/edd";

interface CaseWorkspaceProps {
  selectedCase: CaseDetail | null;
  selectedFixture: FixtureMeta | null;
  isUploading: boolean;
  isAnalyzing: boolean;
  riskLevel: string | null;
  onUpload: (files: File[]) => Promise<void>;
  onAnalyze: () => void;
  liveTrace?: LiveAgentEvent[];
  liveStage?: LiveAgentStage;
  useAgentLoop?: boolean;
}

const RISK_VARIANT: Record<string, "success" | "warning" | "danger" | "secondary"> = {
  low: "success",
  medium: "warning",
  high: "danger",
  pending: "secondary",
};

export function CaseWorkspace({
  selectedCase,
  selectedFixture,
  isUploading,
  isAnalyzing,
  riskLevel,
  onUpload,
  onAnalyze,
  liveTrace = [],
  liveStage = "idle",
  useAgentLoop = false,
}: CaseWorkspaceProps) {
  const showLivePanel = useAgentLoop && (isAnalyzing || liveTrace.length > 0);
  if (!selectedCase && !selectedFixture) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center p-8">
        <CircleDashed className="size-8 text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">
          Create a new case or pick a demo scenario from the sidebar.
        </p>
      </div>
    );
  }

  // Demo fixture mode — no upload UI, just an Analyze button
  if (selectedFixture) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-4 py-3 border-b border-border bg-card/30 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-semibold truncate">{selectedFixture.label}</div>
            <div className="text-xs text-muted-foreground truncate">
              {selectedFixture.scenario} — {selectedFixture.description}
            </div>
          </div>
          <Button
            size="sm"
            onClick={onAnalyze}
            disabled={isAnalyzing}
            className="gap-1.5 shrink-0"
          >
            {isAnalyzing ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Play className="size-3.5" />
            )}
            Run Analysis
          </Button>
        </div>
        <div className="flex-1 flex items-center justify-center text-xs text-muted-foreground p-8 text-center">
          Fixture-based demo. Click <span className="font-medium mx-1">Run Analysis</span> to
          resolve UBOs, screen OFAC/PEP/Adverse Media, and draft the memo.
        </div>
      </div>
    );
  }

  const c = selectedCase!;
  const hasDocs = c.documents.length > 0;
  const hasGraph = c.extracted_entities.length > 0;

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-border bg-card/30 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold truncate">{c.name}</div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="text-xs text-muted-foreground">
              {c.document_count} doc{c.document_count !== 1 ? "s" : ""} ·{" "}
              {c.extracted_entities.length} entities
            </span>
            {riskLevel && (
              <Badge variant={RISK_VARIANT[riskLevel] ?? "secondary"} className="text-[10px]">
                {riskLevel} risk
              </Badge>
            )}
          </div>
        </div>
        <Button
          size="sm"
          onClick={onAnalyze}
          disabled={!hasGraph || isAnalyzing || isUploading}
          className="gap-1.5 shrink-0"
        >
          {isAnalyzing ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Sparkles className="size-3.5" />
          )}
          Run Analysis
        </Button>
      </div>

      <div className="p-4">
        <DocumentUpload onUpload={onUpload} isUploading={isUploading} />
      </div>

      {hasDocs && (
        <>
          <div className="px-4 pb-1 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Uploaded
            </span>
            {hasGraph && (
              <Badge variant="secondary" className="text-[10px]">
                Graph extracted
              </Badge>
            )}
          </div>
          <ScrollArea className="flex-1">
            <DocumentList documents={c.documents} />
          </ScrollArea>
        </>
      )}

      {showLivePanel && <LiveAgentPanel trace={liveTrace} stage={liveStage} />}
    </div>
  );
}
