"use client";

import { AppHeader } from "@/components/layout/app-header";
import { useScenario } from "@/components/scenario/use-scenario";
import { AnalysisChatView } from "@/components/case/analysis-chat-view";
import { MemoPanel } from "@/components/memo/memo-panel";
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
          useAgentLoop={s.useAgentLoop}
          onToggleAgentLoop={s.setUseAgentLoop}
          onCreateCase={s.createNewCase}
          onSelectCase={s.selectCase}
          onSelectFixture={s.selectFixture}
        />

        {showAnalysis ? (
          <>
            {/* Middle column: agent chat stream */}
            <div className="flex flex-col flex-1 min-w-0 border-r border-border overflow-hidden">
              <AnalysisChatView
                chatEvents={s.chatEvents}
                liveStage={s.liveStage}
                analysisResult={s.analysisResult}
                isAnalyzing={s.isAnalyzing}
                applicantName={s.selectedCase?.name ?? s.selectedFixture?.label}
                documentCount={s.selectedCase?.documents?.length ?? 0}
                onUpdateSection={s.updateSection}
              />
            </div>

            {/* Right column: CDD checklist, documents, screening, reasoning */}
            <div className="w-[30%] min-w-[300px] max-w-[380px] overflow-hidden">
              <MemoPanel
                analysisResult={s.analysisResult}
                isLoading={s.isAnalyzing}
                documents={s.selectedCase?.documents ?? []}
                onUploadFiles={s.activeCaseId ? s.uploadFiles : undefined}
                isUploading={s.isUploading}
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

    </div>
  );
}
