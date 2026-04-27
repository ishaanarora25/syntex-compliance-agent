"use client";

import {
  FileText,
  Bot,
  CheckCircle2,
  Loader2,
  ShieldCheck,
  ClipboardList,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { UboMemo } from "./ubo-memo";
import { EddMemo } from "./edd-memo";
import { AgentReasoning } from "./agent-reasoning";
import { ScreeningPanel } from "@/components/case/screening-panel";
import { CDDChecklist } from "@/components/case/cdd-checklist";
import type { AnalyzeResponse, MemoSection } from "@/types/edd";

interface MemoPanelProps {
  analysisResult: AnalyzeResponse | null;
  memoSections: MemoSection[];
  isLoading: boolean;
  onUpdateSection: (sectionId: string, content: string) => void;
  onApproveDraft: () => void;
}

export function MemoPanel({
  analysisResult,
  memoSections,
  isLoading,
  onUpdateSection,
  onApproveDraft,
}: MemoPanelProps) {
  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/10">
        <div className="text-center space-y-3">
          <Loader2 className="size-10 text-muted-foreground/40 mx-auto animate-spin" />
          <p className="text-sm text-muted-foreground">
            Resolving UBOs, screening OFAC/PEP/Adverse Media, drafting memo…
          </p>
        </div>
      </div>
    );
  }

  if (!analysisResult) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/10">
        <div className="text-center space-y-2">
          <FileText className="size-10 text-muted-foreground/30 mx-auto" />
          <p className="text-sm text-muted-foreground">
            Run the analysis to generate the memo, screenings, and CDD checklist.
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
        <Button
          size="sm"
          onClick={onApproveDraft}
          className="gap-1.5 bg-green-600 hover:bg-green-700 text-white"
        >
          <CheckCircle2 className="size-3.5" />
          Approve Draft
        </Button>
      </div>

      <div className="flex-1 overflow-hidden">
        <Tabs defaultValue="memo" className="h-full flex flex-col">
          <div className="px-4 pt-3 pb-0 border-b border-border">
            <TabsList className="h-8">
              <TabsTrigger value="memo" className="text-xs gap-1.5">
                <FileText className="size-3" />
                {analysisResult.memo_type === "full_edd" ? "EDD Memo" : "UBO Memo"}
              </TabsTrigger>
              <TabsTrigger value="screening" className="text-xs gap-1.5">
                <ShieldCheck className="size-3" />
                Screening
              </TabsTrigger>
              <TabsTrigger value="checklist" className="text-xs gap-1.5">
                <ClipboardList className="size-3" />
                CDD Checklist
              </TabsTrigger>
              <TabsTrigger value="reasoning" className="text-xs gap-1.5">
                <Bot className="size-3" />
                Reasoning
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="memo" className="flex-1 overflow-hidden mt-0">
            <ScrollArea className="h-full">
              <div className="p-4">
                {analysisResult.memo_type === "full_edd" ? (
                  <EddMemo
                    result={analysisResult}
                    memoSections={memoSections}
                    onUpdateSection={onUpdateSection}
                  />
                ) : (
                  <UboMemo
                    result={analysisResult}
                    memoSections={memoSections}
                    onUpdateSection={onUpdateSection}
                  />
                )}
              </div>
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
              <div className="p-4">
                <AgentReasoning workProduct={analysisResult.agent_work_product} />
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
