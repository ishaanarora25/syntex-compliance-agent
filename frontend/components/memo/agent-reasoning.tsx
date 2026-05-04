"use client";

import {
  FileText,
  Users,
  GitBranch,
  Shield,
  Calculator,
  Search,
  AlertOctagon,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import type {
  AgentWorkProduct,
  AgentReasoningStep,
  AgentTrace,
  VerifierReport,
} from "@/types/edd";

const STEP_ICONS: Record<string, React.ElementType> = {
  document_review: FileText,
  entity_extraction: Users,
  ownership_mapping: GitBranch,
  trust_analysis: Shield,
  ubo_calculation: Calculator,
  ofac_screening: Search,
  risk_assessment: AlertOctagon,
  conclusion: CheckCircle2,
};

const STEP_COLORS: Record<string, string> = {
  document_review: "text-blue-500",
  entity_extraction: "text-violet-500",
  ownership_mapping: "text-indigo-500",
  trust_analysis: "text-orange-500",
  ubo_calculation: "text-emerald-500",
  ofac_screening: "text-amber-500",
  risk_assessment: "text-red-500",
  conclusion: "text-green-600",
};

const STEP_BG: Record<string, string> = {
  document_review: "bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800",
  entity_extraction: "bg-violet-50 dark:bg-violet-950/30 border-violet-200 dark:border-violet-800",
  ownership_mapping: "bg-indigo-50 dark:bg-indigo-950/30 border-indigo-200 dark:border-indigo-800",
  trust_analysis: "bg-orange-50 dark:bg-orange-950/30 border-orange-200 dark:border-orange-800",
  ubo_calculation: "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800",
  ofac_screening: "bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800",
  risk_assessment: "bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800",
  conclusion: "bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800",
};

function ReasoningStep({ step }: { step: AgentReasoningStep }) {
  const [expanded, setExpanded] = useState(step.category === "conclusion" || step.category === "risk_assessment");
  const Icon = STEP_ICONS[step.category] ?? FileText;
  const color = STEP_COLORS[step.category] ?? "text-muted-foreground";
  const bg = STEP_BG[step.category] ?? "bg-muted/30 border-border";

  return (
    <div className={cn("rounded-lg border p-3 transition-colors", bg)}>
      <button
        className="w-full flex items-start gap-2.5 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <Icon className={cn("size-3.5 shrink-0 mt-0.5", color)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 min-w-0">
            <span className="text-xs font-semibold text-foreground leading-tight truncate">
              Step {step.step_number}: {step.title}
            </span>
            {expanded ? (
              <ChevronDown className="size-3 text-muted-foreground shrink-0" />
            ) : (
              <ChevronRight className="size-3 text-muted-foreground shrink-0" />
            )}
          </div>
          {!expanded && (
            <p className="text-[10px] text-muted-foreground mt-0.5 truncate">{step.outcome}</p>
          )}
        </div>
      </button>

      {expanded && (
        <div className="mt-2.5 ml-6 space-y-2" style={{ minWidth: 0, overflow: "hidden" }}>
          <p className="text-[11px] text-foreground/80 leading-relaxed" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", wordBreak: "break-word" }}>
            {step.detail}
          </p>
          <div className="flex items-start gap-1.5 pt-1 border-t border-current/10">
            <CheckCircle2 className={cn("size-3 shrink-0 mt-0.5", color)} />
            <p className={cn("text-[11px] font-medium leading-tight", color)} style={{ overflowWrap: "anywhere" }}>{step.outcome}</p>
          </div>
        </div>
      )}
    </div>
  );
}

interface AgentReasoningProps {
  workProduct: AgentWorkProduct;
  agentTrace?: AgentTrace | null;
  verifierReport?: VerifierReport | null;
}

const CONCLUSION_BADGE: Record<string, "success" | "warning" | "danger"> = {
  "Recommend Approval": "success",
  "Recommend Approval with Enhanced Documentation": "warning",
  "Escalate for EDD Review": "danger",
  "Refer to Compliance": "danger",
};

export function AgentReasoning({
  workProduct,
  agentTrace,
  verifierReport,
}: AgentReasoningProps) {
  const badgeVariant = CONCLUSION_BADGE[workProduct.conclusion] ?? "secondary";

  return (
    <div className="space-y-4" style={{ minWidth: 0, overflow: "hidden" }}>
      {agentTrace && <AgentTraceBlock trace={agentTrace} />}
      {verifierReport && <VerifierReportBlock report={verifierReport} />}
      {/* Summary header */}
      <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-2 min-w-0 overflow-hidden">
        <div className="flex items-start justify-between gap-2 min-w-0">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-foreground">Agent Reasoning Summary</p>
            <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed break-words">
              {workProduct.summary}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap pt-1 min-w-0">
          <Badge variant={badgeVariant} className="text-xs max-w-full whitespace-normal break-words">
            {workProduct.conclusion}
          </Badge>
          <span className="text-[10px] text-muted-foreground">
            {workProduct.total_ubos_resolved} UBO{workProduct.total_ubos_resolved !== 1 ? "s" : ""} resolved
          </span>
          {workProduct.risk_flags_found.length > 0 && (
            <div className="flex items-baseline gap-1 flex-wrap min-w-0 basis-full">
              <span className="text-[10px] text-red-600 dark:text-red-400 shrink-0">
                {workProduct.risk_flags_found.length} risk flag{workProduct.risk_flags_found.length !== 1 ? "s" : ""}:
              </span>
              {workProduct.risk_flags_found.map((flag) => (
                <span
                  key={flag}
                  className="text-[10px] text-red-600 dark:text-red-400 break-words"
                >
                  {flag}
                </span>
              ))}
            </div>
          )}
        </div>
        <p className="text-[10px] text-muted-foreground border-t border-border/50 pt-2 mt-1 break-words">
          This reasoning trace documents every step taken by the AI system. Review and approve to confirm you have
          assessed the analysis and agree with the conclusion.
        </p>
      </div>

      <Separator />

      {/* Step-by-step reasoning */}
      <div className="space-y-2">
        {workProduct.steps.map((step) => (
          <ReasoningStep key={step.step_number} step={step} />
        ))}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Agent trace (only shown when the agent loop endpoint produced the response)
// ---------------------------------------------------------------------------

const STOP_REASON_LABEL: Record<string, string> = {
  finalized: "Finalized cleanly",
  max_iterations: "Hit iteration cap",
  ended_naturally: "Ended without finalize",
  error: "Errored",
};

function AgentTraceBlock({ trace }: { trace: AgentTrace }) {
  const [expanded, setExpanded] = useState(false);
  const errorCount = trace.tool_calls.filter((c) => c.is_error).length;
  return (
    <div className="rounded-lg border border-primary/40 bg-primary/5 p-3 space-y-2 min-w-0 overflow-hidden">
      <button
        className="w-full flex items-start justify-between gap-2 text-left min-w-0"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-start gap-2 min-w-0 flex-1">
          <Search className="size-3.5 text-primary shrink-0 mt-0.5" />
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-foreground">Agent tool trace</p>
            <p className="text-[10px] text-muted-foreground break-words">
              {trace.tool_calls.length} tool call{trace.tool_calls.length !== 1 ? "s" : ""} ·
              {" "}{trace.iterations} iteration{trace.iterations !== 1 ? "s" : ""} ·
              {" "}{STOP_REASON_LABEL[trace.stop_reason] ?? trace.stop_reason}
              {trace.revision_rounds > 0 && (
                <> · {trace.revision_rounds} verifier revision{trace.revision_rounds !== 1 ? "s" : ""}</>
              )}
              {errorCount > 0 && (
                <span className="text-red-600 dark:text-red-400"> · {errorCount} error{errorCount !== 1 ? "s" : ""}</span>
              )}
            </p>
          </div>
        </div>
        {expanded ? (
          <ChevronDown className="size-3 text-muted-foreground shrink-0 mt-1" />
        ) : (
          <ChevronRight className="size-3 text-muted-foreground shrink-0 mt-1" />
        )}
      </button>

      {expanded && (
        <div style={{ maxHeight: "24rem", overflowY: "auto", overflowX: "hidden" }} className="space-y-1 pt-1 border-t border-border/50">
          {trace.tool_calls.map((call, idx) => (
            <div
              key={`${call.tool_use_id}-${idx}`}
              className={cn(
                "rounded-md border px-2 py-1.5 text-[10px]",
                call.is_error
                  ? "border-red-300 bg-red-50/60 dark:bg-red-950/30"
                  : "border-border bg-background/60"
              )}
              style={{ overflow: "hidden" }}
            >
              <div className="flex items-center justify-between gap-2 min-w-0">
                <span className="font-mono font-semibold text-foreground truncate">
                  #{idx + 1} · iter {call.iteration} · {call.name}
                </span>
                <span className="text-muted-foreground shrink-0">{call.duration_ms}ms</span>
              </div>
              {Object.keys(call.input).length > 0 && (
                <p className="mt-0.5 text-muted-foreground font-mono" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", wordBreak: "break-word" }}>
                  in: {JSON.stringify(call.input)}
                </p>
              )}
              <p className="mt-0.5 text-foreground/80" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", wordBreak: "break-word" }}>
                out: {call.output_summary}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Verifier report (self-critique findings)
// ---------------------------------------------------------------------------

function VerifierReportBlock({ report }: { report: VerifierReport }) {
  const [expanded, setExpanded] = useState(report.needs_revision);
  const total =
    report.claims_unsupported.length +
    report.risks_unaddressed.length +
    report.citations_missing.length;
  if (total === 0 && !report.summary) return null;

  return (
    <div
      className={cn(
        "rounded-lg border p-3 space-y-2 min-w-0 overflow-hidden",
        report.needs_revision
          ? "border-amber-300 bg-amber-50/60 dark:bg-amber-950/30"
          : "border-emerald-300 bg-emerald-50/60 dark:bg-emerald-950/30"
      )}
    >
      <button
        className="w-full flex items-start justify-between gap-2 text-left min-w-0"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-start gap-2 min-w-0 flex-1">
          {report.needs_revision ? (
            <AlertOctagon className="size-3.5 text-amber-600 shrink-0 mt-0.5" />
          ) : (
            <CheckCircle2 className="size-3.5 text-emerald-600 shrink-0 mt-0.5" />
          )}
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-foreground">
              Verifier {report.needs_revision ? "flagged issues" : "cleared the memo"}
            </p>
            <p
              className={cn(
                "text-[10px] text-muted-foreground break-words",
                expanded ? "" : "line-clamp-2"
              )}
            >
              {total} finding{total !== 1 ? "s" : ""}
              {report.summary && ` — ${report.summary}`}
            </p>
          </div>
        </div>
        {expanded ? (
          <ChevronDown className="size-3 text-muted-foreground shrink-0 mt-1" />
        ) : (
          <ChevronRight className="size-3 text-muted-foreground shrink-0 mt-1" />
        )}
      </button>

      {expanded && total > 0 && (
        <div className="space-y-2 pt-1 border-t border-current/10 min-w-0">
          {report.claims_unsupported.length > 0 && (
            <FindingGroup title="Claims unsupported" items={report.claims_unsupported} />
          )}
          {report.risks_unaddressed.length > 0 && (
            <FindingGroup title="Risks unaddressed" items={report.risks_unaddressed} />
          )}
          {report.citations_missing.length > 0 && (
            <FindingGroup title="Citations missing" items={report.citations_missing} />
          )}
        </div>
      )}
    </div>
  );
}

const SEVERITY_COLOR: Record<string, string> = {
  low: "text-muted-foreground",
  medium: "text-amber-600",
  high: "text-red-600",
};

function FindingGroup({
  title,
  items,
}: {
  title: string;
  items: VerifierReport["claims_unsupported"];
}) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
        {title}
      </p>
      <ul className="space-y-0.5">
        {items.map((f, i) => (
          <li key={i} className="text-[11px] text-foreground/85 break-words">
            <span className={cn("font-mono mr-1", SEVERITY_COLOR[f.severity] ?? "")}>[{f.severity}]</span>
            {f.section_id && <span className="text-muted-foreground mr-1">({f.section_id})</span>}
            {f.issue}
          </li>
        ))}
      </ul>
    </div>
  );
}
