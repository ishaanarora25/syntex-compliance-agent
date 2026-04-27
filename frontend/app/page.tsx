"use client";

import { AppHeader } from "@/components/layout/app-header";
import { useScenario } from "@/components/scenario/use-scenario";
import { OwnershipGraph } from "@/components/graph/ownership-graph";
import { MemoPanel } from "@/components/memo/memo-panel";
import { AuditStrip } from "@/components/audit/audit-strip";
import { CaseSidebar } from "@/components/case/case-sidebar";
import { HomeView } from "@/components/case/home-view";

export default function HomePage() {
  const s = useScenario();

  // Show analysis layout once analysis is running or complete
  const showAnalysis = s.isAnalyzing || !!s.analysisResult;

  // Files staged without a case go to queueFiles; files added to an existing
  // case upload immediately.
  const handleAddFiles = s.activeCaseId ? s.uploadFiles : s.queueFiles;

  return (
    <div className="flex flex-col h-screen bg-background overflow-hidden">
      <AppHeader />

      <div className="flex flex-1 overflow-hidden">
        <CaseSidebar
          cases={s.cases}
          fixtures={s.fixtures}
          activeCaseId={s.activeCaseId}
          activeFixtureId={s.activeFixtureId}
          isBusy={s.isLoading}
          onCreateCase={s.createNewCase}
          onSelectCase={s.selectCase}
          onSelectFixture={s.selectFixture}
        />

        {showAnalysis ? (
          <>
            {/* Middle column: ownership graph */}
            <div className="flex flex-col flex-1 min-w-0 border-r border-border overflow-hidden">
              <OwnershipGraph
                nodes={s.analysisResult?.graph_nodes ?? []}
                edges={s.analysisResult?.graph_edges ?? []}
                isLoading={s.isAnalyzing}
              />
            </div>

            {/* Right column: memo + screenings + checklist + reasoning */}
            <div className="w-[42%] min-w-[420px] overflow-hidden">
              <MemoPanel
                analysisResult={s.analysisResult}
                memoSections={s.memoSections}
                isLoading={s.isAnalyzing}
                onUpdateSection={s.updateSection}
                onApproveDraft={s.approveDraft}
              />
            </div>
          </>
        ) : (
          <HomeView
            pendingFiles={s.pendingFiles}
            selectedCase={s.selectedCase}
            selectedFixture={s.selectedFixture}
            isUploading={s.isUploading}
            isAnalyzing={s.isAnalyzing}
            onAddFiles={handleAddFiles}
            onRemovePendingFile={s.removePendingFile}
            onAnalyze={s.runAnalysis}
          />
        )}
      </div>

      <AuditStrip entries={s.auditLog} />
    </div>
  );
}
