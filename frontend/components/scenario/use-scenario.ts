"use client";

import { useCallback, useEffect, useState } from "react";
import {
  analyzeCase,
  analyzeFixture,
  approveEdd,
  createCase,
  getCase,
  getCaseAnalysis,
  listCases,
  listFixtures,
  uploadDocuments,
} from "@/lib/api";

import type {
  AnalyzeResponse,
  AuditEntry,
  CaseDetail,
  CaseSummary,
  FixtureMeta,
  MemoSection,
} from "@/types/edd";

type Selection =
  | { kind: "none" }
  | { kind: "case"; caseId: string }
  | { kind: "fixture"; fixtureId: string };

export function useScenario() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [fixtures, setFixtures] = useState<FixtureMeta[]>([]);
  const [selection, setSelection] = useState<Selection>({ kind: "none" });
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [activeFixture, setActiveFixture] = useState<FixtureMeta | null>(null);

  const [analysisResult, setAnalysisResult] = useState<AnalyzeResponse | null>(null);
  const [memoSections, setMemoSections] = useState<MemoSection[]>([]);

  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);

  // Bootstrap cases + fixtures once
  useEffect(() => {
    (async () => {
      try {
        const [cs, fs] = await Promise.all([listCases(), listFixtures()]);
        setCases(cs);
        setFixtures(fs);
      } catch (err) {
        console.error("Bootstrap failed:", err);
      }
    })();
  }, []);

  const refreshCases = useCallback(async () => {
    try {
      setCases(await listCases());
    } catch (err) {
      console.error("listCases failed:", err);
    }
  }, []);

  const selectCase = useCallback(async (caseId: string) => {
    setSelection({ kind: "case", caseId });
    setActiveFixture(null);
    setAnalysisResult(null);
    setMemoSections([]);
    try {
      const [detail, analysis] = await Promise.all([
        getCase(caseId),
        getCaseAnalysis(caseId),
      ]);
      setCaseDetail(detail);
      if (analysis) {
        setAnalysisResult(analysis);
        setMemoSections(analysis.memo_sections);
      }
    } catch (err) {
      console.error("getCase failed:", err);
      alert(`Failed to load case: ${err instanceof Error ? err.message : "Unknown"}`);
    }
  }, []);

  const selectFixture = useCallback(
    (fixtureId: string) => {
      const f = fixtures.find((x) => x.fixture_id === fixtureId) ?? null;
      setActiveFixture(f);
      setCaseDetail(null);
      setSelection({ kind: "fixture", fixtureId });
      setAnalysisResult(null);
      setMemoSections([]);
    },
    [fixtures]
  );

  const createNewCase = useCallback(
    async (name: string) => {
      try {
        const summary = await createCase(name);
        await refreshCases();
        await selectCase(summary.case_id);
      } catch (err) {
        console.error("createCase failed:", err);
        alert(`Failed to create case: ${err instanceof Error ? err.message : "Unknown"}`);
      }
    },
    [refreshCases, selectCase]
  );

  const uploadFiles = useCallback(
    async (files: File[]) => {
      if (selection.kind !== "case") return;
      setIsUploading(true);
      try {
        const result = await uploadDocuments(selection.caseId, files);
        setCaseDetail((prev) =>
          prev
            ? {
                ...prev,
                ...result.case,
                documents: result.documents,
                extracted_entities: result.extracted_entities,
                extracted_edges: result.extracted_edges,
              }
            : prev
        );
        await refreshCases();
      } catch (err) {
        console.error("upload failed:", err);
        alert(`Upload failed: ${err instanceof Error ? err.message : "Unknown"}`);
      } finally {
        setIsUploading(false);
      }
    },
    [selection, refreshCases]
  );

  const queueFiles = useCallback((files: File[]) => {
    const pdfs = files.filter(
      (f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")
    );
    setPendingFiles((prev) => [...prev, ...pdfs]);
  }, []);

  const removePendingFile = useCallback((idx: number) => {
    setPendingFiles((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  const runAnalysis = useCallback(async () => {
    // New case flow: no case/fixture selected, but pending files staged
    if (selection.kind === "none") {
      if (pendingFiles.length === 0) return;
      setIsAnalyzing(true);
      setAnalysisResult(null);
      setMemoSections([]);
      const autoName = `EDD Case — ${new Date().toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })}`;
      try {
        const summary = await createCase(autoName);
        setIsUploading(true);
        await uploadDocuments(summary.case_id, pendingFiles);
        setIsUploading(false);
        setPendingFiles([]);
        setSelection({ kind: "case", caseId: summary.case_id });
        const result = await analyzeCase(summary.case_id);
        setAnalysisResult(result);
        setMemoSections(result.memo_sections);
        await refreshCases();
        try {
          setCaseDetail(await getCase(summary.case_id));
        } catch {
          /* non-fatal */
        }
      } catch (err) {
        console.error("Analysis failed:", err);
        alert(`Analysis failed: ${err instanceof Error ? err.message : "Unknown"}`);
      } finally {
        setIsAnalyzing(false);
        setIsUploading(false);
      }
      return;
    }

    setIsAnalyzing(true);
    setAnalysisResult(null);
    setMemoSections([]);
    try {
      const result =
        selection.kind === "case"
          ? await analyzeCase(selection.caseId)
          : await analyzeFixture(selection.fixtureId);
      setAnalysisResult(result);
      setMemoSections(result.memo_sections);
      if (selection.kind === "case") {
        await refreshCases();
        try {
          setCaseDetail(await getCase(selection.caseId));
        } catch {
          /* non-fatal */
        }
      }
    } catch (err) {
      console.error("Analysis failed:", err);
      alert(`Analysis failed: ${err instanceof Error ? err.message : "Unknown"}`);
    } finally {
      setIsAnalyzing(false);
    }
  }, [selection, pendingFiles, refreshCases]);

  const approveDraft = useCallback(async () => {
    if (!analysisResult) return;
    try {
      const entry = await approveEdd({
        case_id: analysisResult.case_id,
        fixture_id: analysisResult.fixture_id,
        approved_by: "Demo Analyst",
        memo_snapshot: memoSections,
        conclusion: analysisResult.agent_work_product.conclusion,
      });
      setAuditLog((prev) => [entry, ...prev]);
    } catch (err) {
      console.error("Approval failed:", err);
      alert(`Approval failed: ${err instanceof Error ? err.message : "Unknown"}`);
    }
  }, [analysisResult, memoSections]);

  const updateSection = useCallback((sectionId: string, content: string) => {
    setMemoSections((prev) =>
      prev.map((s) => (s.section_id === sectionId ? { ...s, content } : s))
    );
  }, []);

  const activeCaseId = selection.kind === "case" ? selection.caseId : null;
  const activeFixtureId = selection.kind === "fixture" ? selection.fixtureId : null;

  return {
    cases,
    fixtures,
    selectedCase: caseDetail,
    selectedFixture: activeFixture,
    activeCaseId,
    activeFixtureId,
    pendingFiles,
    analysisResult,
    memoSections,
    isUploading,
    isAnalyzing,
    isLoading: isUploading || isAnalyzing,
    auditLog,
    createNewCase,
    selectCase,
    selectFixture,
    uploadFiles,
    queueFiles,
    removePendingFile,
    runAnalysis,
    approveDraft,
    updateSection,
  };
}
