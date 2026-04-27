import type {
  AnalyzeResponse,
  AuditEntry,
  CaseDetail,
  CaseSummary,
  FixtureMeta,
  MemoSection,
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

// ---------------------------------------------------------------------------
// Approval / audit
// ---------------------------------------------------------------------------

export async function approveEdd(params: {
  case_id?: string;
  fixture_id?: string;
  approved_by: string;
  memo_snapshot: MemoSection[];
  conclusion: string;
}): Promise<AuditEntry> {
  const res = await fetch(`${EDD}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error("Approval failed");
  const data = await res.json();
  return data.entry;
}

export async function getAuditLog(): Promise<AuditEntry[]> {
  const res = await fetch(`${EDD}/audit`);
  if (!res.ok) throw new Error("Failed to fetch audit log");
  const data = await res.json();
  return data.entries;
}
