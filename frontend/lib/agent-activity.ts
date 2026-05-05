// Maps raw MCP tool names to non-technical activity labels for the live UI.
// The model is told not to name tools in narration; the UI honors the same
// rule so users watching the live trace never see `screen_ofac` either.

const TOOL_LABELS: Record<string, string> = {
  list_documents: "Reviewing uploaded documents",
  read_document: "Reading document",
  extract_subgraph: "Mapping ownership structure",
  resolve_ownership: "Resolving beneficial owners",
  screen_ofac: "Checking sanctions list",
  screen_pep: "Checking politically-exposed persons",
  screen_adverse_media: "Checking adverse media",
  mark_required_document: "Flagging required document",
  note: "Recording note",
  lookup_fincen_rule: "Consulting FinCEN rules",
  draft_justification: "Drafting intake justification",
  recommend_escalation: "Recommending escalation",
  finalize: "Finalizing case",
};

export function activityLabel(
  toolName: string,
  input?: Record<string, unknown>
): string {
  const base = TOOL_LABELS[toolName] ?? "Working";
  if (!input) return base;
  const subject =
    typeof input.name === "string"
      ? input.name
      : typeof input.label === "string"
      ? (input.label as string)
      : null;
  if (subject && subject.length <= 60) return `${base} — ${subject}`;
  return base;
}
