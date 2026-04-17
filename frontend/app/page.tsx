"use client";

import { AppHeader } from "@/components/layout/app-header";
import { ScenarioControls } from "@/components/scenario/scenario-controls";
import { useScenario } from "@/components/scenario/use-scenario";
import { OwnershipGraph } from "@/components/graph/ownership-graph";
import { MemoPanel } from "@/components/memo/memo-panel";
import { AuditStrip } from "@/components/audit/audit-strip";

export default function HomePage() {
  const scenario = useScenario();

  return (
    <div className="flex flex-col h-screen bg-background overflow-hidden">
      <AppHeader />

      <div className="border-b border-border px-6 py-3">
        <ScenarioControls
          isLoading={scenario.isLoading}
          activeFixtureId={scenario.analysisResult?.fixture_id ?? null}
          riskLevel={scenario.analysisResult?.risk_level ?? null}
          onLoadScenario={scenario.loadScenario}
        />
      </div>

      {/* Main split panel */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Ownership Graph */}
        <div className="w-1/2 border-r border-border overflow-hidden">
          <OwnershipGraph
            nodes={scenario.analysisResult?.graph_nodes ?? []}
            edges={scenario.analysisResult?.graph_edges ?? []}
            isLoading={scenario.isLoading}
          />
        </div>

        {/* Right: Memo + Reasoning Panel */}
        <div className="w-1/2 overflow-hidden">
          <MemoPanel
            analysisResult={scenario.analysisResult}
            memoSections={scenario.memoSections}
            isLoading={scenario.isLoading}
            onUpdateSection={scenario.updateSection}
            onApproveDraft={scenario.approveDraft}
          />
        </div>
      </div>

      {/* Bottom: Audit log strip */}
      <AuditStrip entries={scenario.auditLog} />
    </div>
  );
}
