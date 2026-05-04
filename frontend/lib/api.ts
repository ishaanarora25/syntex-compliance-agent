import type {
  AnalyzeResponse,
  CaseDetail,
  CaseSummary,
  FixtureMeta,
  UploadDocumentsResponse,
} from "@/types/edd";

const EDD = "/api/backend/edd";
const CASES = "/api/backend/cases";

// ---------------------------------------------------------------------------
// Fixtures (legacy demo path)
// ---------------------------------------------------------------------------

export async function listFixtures(): Promise<FixtureMeta[]> {
  const res = await fetch(`${EDD}/fixtures`);
  if (!res.ok) throw new Error("Failed to fetch fixtures");
  const data = await res.json();
  return data.fixtures;
}

export async function analyzeFixture(fixtureId: string): Promise<AnalyzeResponse> {
  return analyze({ fixture_id: fixtureId });
}

// ---------------------------------------------------------------------------
// Cases
// ---------------------------------------------------------------------------

export async function listCases(): Promise<CaseSummary[]> {
  const res = await fetch(CASES);
  if (!res.ok) throw new Error("Failed to fetch cases");
  const data = await res.json();
  return data.cases;
}

export async function createCase(name: string): Promise<CaseSummary> {
  const res = await fetch(CASES, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error("Failed to create case");
  const data = await res.json();
  return data.case;
}

export async function getCase(caseId: string): Promise<CaseDetail> {
  const res = await fetch(`${CASES}/${caseId}`);
  if (!res.ok) throw new Error("Failed to fetch case");
  return res.json();
}

export async function getCaseAnalysis(caseId: string): Promise<AnalyzeResponse | null> {
  const res = await fetch(`${CASES}/${caseId}/analysis`);
  if (res.status === 204) return null;
  if (!res.ok) throw new Error("Failed to fetch case analysis");
  return res.json();
}

export async function uploadDocuments(
  caseId: string,
  files: File[]
): Promise<UploadDocumentsResponse> {
  const form = new FormData();
  for (const f of files) {
    form.append("files", f);
  }
  const res = await fetch(`${CASES}/${caseId}/documents`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message ?? err.detail ?? "Upload failed");
  }
  return res.json();
}

export async function analyzeCase(caseId: string): Promise<AnalyzeResponse> {
  return analyze({ case_id: caseId });
}

export async function analyzeCaseAgent(caseId: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${EDD}/analyze-agent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: caseId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message ?? err.detail ?? "Agent analysis failed");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Streaming agent loop — Server-Sent Events
// ---------------------------------------------------------------------------

export type AgentStreamEvent =
  | { type: "started"; case_id: string; applicant: string; document_count: number }
  | { type: "iteration"; iteration: number }
  | {
      type: "tool_use";
      iteration: number;
      name: string;
      input: Record<string, unknown>;
      tool_use_id: string;
    }
  | {
      type: "tool_result";
      iteration: number;
      name: string;
      output_summary: string;
      is_error: boolean;
      duration_ms: number;
    }
  | { type: "assistant_text"; text: string }
  | { type: "post_processing"; stop_reason: string; iterations: number }
  | { type: "verifier_start" }
  | { type: "verifier_revision"; round: number; summary: string }
  | { type: "verifier_done"; needs_revision: boolean; summary: string; revision_rounds: number }
  | { type: "final"; response: AnalyzeResponse }
  | { type: "error"; message: string };

/**
 * Run the agent loop with live SSE updates. `onEvent` is invoked for every
 * intermediate event; the resolved value is the final AnalyzeResponse.
 * Throws on `error` events or transport failures.
 */
export async function analyzeCaseAgentStream(
  caseId: string,
  onEvent: (event: AgentStreamEvent) => void
): Promise<AnalyzeResponse> {
  const res = await fetch(`${EDD}/analyze-agent/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: caseId }),
  });
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message ?? err.detail ?? "Agent stream failed to start");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: AnalyzeResponse | null = null;
  let errorMessage: string | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE event boundary is a blank line.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);

      // Concatenate all `data:` lines in the event.
      const dataLines = raw
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trimStart());
      if (dataLines.length === 0) continue;
      const json = dataLines.join("\n");
      let event: AgentStreamEvent;
      try {
        event = JSON.parse(json) as AgentStreamEvent;
      } catch {
        console.warn("Malformed SSE event:", json);
        continue;
      }

      onEvent(event);

      if (event.type === "final") final = event.response;
      else if (event.type === "error") errorMessage = event.message;
    }
  }

  if (errorMessage) throw new Error(errorMessage);
  if (!final) throw new Error("Agent stream ended without a final event.");
  return final;
}

async function analyze(body: { fixture_id?: string; case_id?: string }): Promise<AnalyzeResponse> {
  const res = await fetch(`${EDD}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message ?? err.detail ?? "Analysis failed");
  }
  return res.json();
}

