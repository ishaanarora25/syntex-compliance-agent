"use client";

import { FileText, Bot, CheckCircle2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { UboMemo } from "./ubo-memo";
import { EddMemo } from "./edd-memo";
import { AgentReasoning } from "./agent-reasoning";
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
          <p className="text-sm text-muted-foreground">Analyzing — resolving UBOs, screening OFAC, drafting memo…</p>
        </div>
      </div>
    );
  }

  if (!analysisResult) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/10">
        <div className="text-center space-y-2">
          <FileText className="size-10 text-muted-foreground/30 mx-auto" />
          <p className="text-sm text-muted-foreground">Load a scenario to generate the EDD analysis</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Action bar */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-card/50">
        <div className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground">{analysisResult.fixture_id.replace("fixture_", "Fixture ").toUpperCase()}</span>
          {" "}— {analysisResult.processing_ms}ms
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

      {/* Tabs */}
      <div className="flex-1 overflow-hidden">
        <Tabs defaultValue="memo" className="h-full flex flex-col">
          <div className="px-4 pt-3 pb-0 border-b border-border">
            <TabsList className="h-8">
              <TabsTrigger value="memo" className="text-xs gap-1.5">
                <FileText className="size-3" />
                {analysisResult.memo_type === "full_edd" ? "EDD Memo" : "UBO Resolution Memo"}
              </TabsTrigger>
              <TabsTrigger value="reasoning" className="text-xs gap-1.5">
                <Bot className="size-3" />
                Agent Reasoning
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
