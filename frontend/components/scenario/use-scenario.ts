"use client";

import { useState, useCallback } from "react";
import { analyzeFixture, approveEdd } from "@/lib/api";
import type { AnalyzeResponse, AuditEntry, MemoSection } from "@/types/edd";

export function useScenario() {
  const [analysisResult, setAnalysisResult] = useState<AnalyzeResponse | null>(null);
  const [memoSections, setMemoSections] = useState<MemoSection[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);

  const loadScenario = useCallback(async (fixtureId: string) => {
    setIsLoading(true);
    setAnalysisResult(null);
    setMemoSections([]);
    try {
      const result = await analyzeFixture(fixtureId);
      setAnalysisResult(result);
      setMemoSections(result.memo_sections);
    } catch (err) {
      console.error("Analysis failed:", err);
      alert(`Analysis failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const approveDraft = useCallback(async () => {
    if (!analysisResult) return;
    try {
      const entry = await approveEdd({
        fixture_id: analysisResult.fixture_id,
        approved_by: "Demo Analyst",
        memo_snapshot: memoSections,
        conclusion: analysisResult.agent_work_product.conclusion,
      });
      setAuditLog((prev) => [entry, ...prev]);
    } catch (err) {
      console.error("Approval failed:", err);
      alert(`Approval failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    }
  }, [analysisResult, memoSections]);

  const updateSection = useCallback((sectionId: string, content: string) => {
    setMemoSections((prev) =>
      prev.map((s) => (s.section_id === sectionId ? { ...s, content } : s))
    );
  }, []);

  return {
    analysisResult,
    memoSections,
    isLoading,
    auditLog,
    loadScenario,
    approveDraft,
    updateSection,
  };
}
