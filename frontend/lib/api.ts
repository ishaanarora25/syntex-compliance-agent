import type { AnalyzeResponse, AuditEntry, FixtureMeta, MemoSection } from "@/types/edd";

const BASE = "/api/backend/edd";

export async function listFixtures(): Promise<FixtureMeta[]> {
  const res = await fetch(`${BASE}/fixtures`);
  if (!res.ok) throw new Error("Failed to fetch fixtures");
  const data = await res.json();
  return data.fixtures;
}

export async function analyzeFixture(fixtureId: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fixture_id: fixtureId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message ?? "Analysis failed");
  }
  return res.json();
}

export async function approveEdd(params: {
  fixture_id: string;
  approved_by: string;
  memo_snapshot: MemoSection[];
  conclusion: string;
}): Promise<AuditEntry> {
  const res = await fetch(`${BASE}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error("Approval failed");
  const data = await res.json();
  return data.entry;
}

export async function getAuditLog(): Promise<AuditEntry[]> {
  const res = await fetch(`${BASE}/audit`);
  if (!res.ok) throw new Error("Failed to fetch audit log");
  const data = await res.json();
  return data.entries;
}
