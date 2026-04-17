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
import type { AgentWorkProduct, AgentReasoningStep } from "@/types/edd";

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
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold text-foreground leading-tight">
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
        <div className="mt-2.5 ml-6 space-y-2">
          <pre className="text-[11px] text-foreground/80 whitespace-pre-wrap font-sans leading-relaxed">
            {step.detail}
          </pre>
          <div className="flex items-start gap-1.5 pt-1 border-t border-current/10">
            <CheckCircle2 className={cn("size-3 shrink-0 mt-0.5", color)} />
            <p className={cn("text-[11px] font-medium leading-tight", color)}>{step.outcome}</p>
          </div>
        </div>
      )}
    </div>
  );
}

interface AgentReasoningProps {
  workProduct: AgentWorkProduct;
}

const CONCLUSION_BADGE: Record<string, "success" | "warning" | "danger"> = {
  "Recommend Approval": "success",
  "Recommend Approval with Enhanced Documentation": "warning",
  "Escalate for EDD Review": "danger",
  "Refer to Compliance": "danger",
};

export function AgentReasoning({ workProduct }: AgentReasoningProps) {
  const badgeVariant = CONCLUSION_BADGE[workProduct.conclusion] ?? "secondary";

  return (
    <div className="space-y-4">
      {/* Summary header */}
      <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-xs font-semibold text-foreground">Agent Reasoning Summary</p>
            <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">
              {workProduct.summary}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap pt-1">
          <Badge variant={badgeVariant} className="text-xs">
            {workProduct.conclusion}
          </Badge>
          <span className="text-[10px] text-muted-foreground">
            {workProduct.total_ubos_resolved} UBO{workProduct.total_ubos_resolved !== 1 ? "s" : ""} resolved
          </span>
          {workProduct.risk_flags_found.length > 0 && (
            <span className="text-[10px] text-red-600 dark:text-red-400">
              {workProduct.risk_flags_found.length} risk flag{workProduct.risk_flags_found.length !== 1 ? "s" : ""}:
              {" "}{workProduct.risk_flags_found.join(", ")}
            </span>
          )}
        </div>
        <p className="text-[10px] text-muted-foreground border-t border-border/50 pt-2 mt-1">
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
