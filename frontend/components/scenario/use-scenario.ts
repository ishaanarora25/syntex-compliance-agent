"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  analyzeCase,
  analyzeCaseAgentStream,
  analyzeFixture,
  createCase,
  getCase,
  getCaseAnalysis,
  listCases,
  listFixtures,
  uploadDocuments,
  type AgentStreamEvent,
} from "@/lib/api";

import type {
  AnalyzeResponse,
  CaseDetail,
  CaseSummary,
  FixtureMeta,
  MemoSection,
} from "@/types/edd";

type Selection =
  | { kind: "none" }
  | { kind: "case"; caseId: string }
  | { kind: "fixture"; fixtureId: string };

export type LiveAgentEvent = {
  tool_use_id: string;
  iteration: number;
  name: string;
  input: Record<string, unknown>;
  status: "running" | "done" | "error";
  output_summary?: string;
  duration_ms?: number;
};

export type LiveTextEvent = { id: string; text: string };
export type ChatEvent =
  | { kind: "tool"; event: LiveAgentEvent }
  | { kind: "text"; event: LiveTextEvent };

export type LiveAgentStage =
  | "idle"
  | "running"
  | "post_processing"
  | "verifying"
  | "verifier_done"
  | "done"
  | "error";

export type LiveStartInfo = {
  applicant: string;
  documentCount: number;
};

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

  // Live agent activity (only populated while a streaming run is in flight).
  // Each tool_use event appends; the matching tool_result event mutates the
  // entry in place via tool_use_id. Cleared at the start of every run.
  const [liveTrace, setLiveTrace] = useState<LiveAgentEvent[]>([]);
  const [liveStage, setLiveStage] = useState<LiveAgentStage>("idle");
  const [liveStart, setLiveStart] = useState<LiveStartInfo | null>(null);
  // Unified chat timeline: interleaved text narration + tool call entries.
  const [chatEvents, setChatEvents] = useState<ChatEvent[]>([]);
  // Map tool_use_id → array index, kept in a ref so onEvent can mutate the
  // existing entry without provoking stale-closure issues.
  const liveIndexRef = useRef<Map<string, number>>(new Map());

  // Whether to drive analysis through the agent loop (Opus + tool use) or
  // through the deterministic legacy pipeline. Default reads from env so the
  // demo can be swapped without code changes.
  const agentDefault =
    typeof process !== "undefined" &&
    process.env?.NEXT_PUBLIC_AGENT_DEFAULT === "false"
      ? false
      : true;
  const [useAgentLoop, setUseAgentLoop] = useState<boolean>(agentDefault);

  const resetLiveTrace = useCallback(() => {
    liveIndexRef.current = new Map();
    setLiveTrace([]);
    setChatEvents([]);
    setLiveStage("idle");
    setLiveStart(null);
  }, []);

  const handleAgentEvent = useCallback((event: AgentStreamEvent) => {
    switch (event.type) {
      case "started":
        setLiveStage("running");
        setLiveStart({
          applicant: event.applicant,
          documentCount: event.document_count,
        });
        break;
      case "tool_use": {
        const entry: LiveAgentEvent = {
          tool_use_id: event.tool_use_id,
          iteration: event.iteration,
          name: event.name,
          input: event.input,
          status: "running",
        };
        setLiveTrace((prev) => {
          liveIndexRef.current.set(event.tool_use_id, prev.length);
          return [...prev, entry];
        });
        setChatEvents((prev) => [...prev, { kind: "tool", event: entry }]);
        break;
      }
      case "tool_result": {
        // Match the most recent running entry with this tool name in the same
        // iteration — we don't get tool_use_id back on the result event, so
        // resolve it by walking from the tail.
        setLiveTrace((prev) => {
          for (let i = prev.length - 1; i >= 0; i--) {
            const e = prev[i];
            if (
              e.status === "running" &&
              e.name === event.name &&
              e.iteration === event.iteration
            ) {
              const next = prev.slice();
              next[i] = {
                ...e,
                status: event.is_error ? "error" : "done",
                output_summary: event.output_summary,
                duration_ms: event.duration_ms,
              };
              return next;
            }
          }
          return prev;
        });
        setChatEvents((prev) => {
          for (let i = prev.length - 1; i >= 0; i--) {
            const item = prev[i];
            if (
              item.kind === "tool" &&
              item.event.status === "running" &&
              item.event.name === event.name &&
              item.event.iteration === event.iteration
            ) {
              const next = prev.slice();
              next[i] = {
                kind: "tool",
                event: {
                  ...item.event,
                  status: event.is_error ? "error" : "done",
                  output_summary: event.output_summary,
                  duration_ms: event.duration_ms,
                },
              };
              return next;
            }
          }
          return prev;
        });
        break;
      }
      case "assistant_text": {
        setChatEvents((prev) => [
          ...prev,
          {
            kind: "text",
            event: { id: Math.random().toString(36).slice(2), text: event.text },
          },
        ]);
        break;
      }
      case "post_processing":
        setLiveStage("post_processing");
        break;
      case "verifier_start":
        setLiveStage("verifying");
        break;
      case "verifier_done":
        setLiveStage("verifier_done");
        break;
      case "final":
        setLiveStage("done");
        break;
      case "error":
        setLiveStage("error");
        break;
      default:
        break;
    }
  }, []);

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
        setMemoSections(analysis.justification_sections ?? []);
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
      const caseId = selection.caseId;
      const hadAnalysis = analysisResult !== null;
      setIsUploading(true);
      try {
        const result = await uploadDocuments(caseId, files);
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
        setIsUploading(false);
        return;
      }
      setIsUploading(false);

      // If analysis was already shown for this case, re-run it so the agent
      // incorporates the newly uploaded documents.
      if (!hadAnalysis) return;
      setIsAnalyzing(true);
      if (useAgentLoop) resetLiveTrace();
      try {
        const updated = useAgentLoop
          ? await analyzeCaseAgentStream(caseId, handleAgentEvent)
          : await analyzeCase(caseId);
        setAnalysisResult(updated);
        setMemoSections(updated.justification_sections ?? []);
        await refreshCases();
        try {
          setCaseDetail(await getCase(caseId));
        } catch {
          /* non-fatal */
        }
      } catch (err) {
        console.error("Re-analysis failed:", err);
        alert(`Re-analysis failed: ${err instanceof Error ? err.message : "Unknown"}`);
      } finally {
        setIsAnalyzing(false);
      }
    },
    [selection, analysisResult, refreshCases, useAgentLoop, resetLiveTrace, handleAgentEvent]
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
      if (useAgentLoop) resetLiveTrace();
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
        const result = useAgentLoop
          ? await analyzeCaseAgentStream(summary.case_id, handleAgentEvent)
          : await analyzeCase(summary.case_id);
        setAnalysisResult(result);
        setMemoSections(result.justification_sections ?? []);
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
    if (useAgentLoop && selection.kind === "case") resetLiveTrace();
    try {
      const result =
        selection.kind === "case"
          ? useAgentLoop
            ? await analyzeCaseAgentStream(selection.caseId, handleAgentEvent)
            : await analyzeCase(selection.caseId)
          : await analyzeFixture(selection.fixtureId);
      setAnalysisResult(result);
      setMemoSections(result.justification_sections ?? []);
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
  }, [selection, pendingFiles, refreshCases, useAgentLoop, resetLiveTrace, handleAgentEvent]);

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
    useAgentLoop,
    setUseAgentLoop,
    liveTrace,
    liveStage,
    liveStart,
    chatEvents,
    createNewCase,
    selectCase,
    selectFixture,
    uploadFiles,
    queueFiles,
    removePendingFile,
    runAnalysis,
    updateSection,
  };
}
