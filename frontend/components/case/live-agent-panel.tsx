"use client";

import { CheckCircle2, Loader2, AlertCircle, Sparkles } from "lucide-react";
import type { LiveAgentEvent, LiveAgentStage } from "@/components/scenario/use-scenario";

interface LiveAgentPanelProps {
  trace: LiveAgentEvent[];
  stage: LiveAgentStage;
}

const STAGE_LABEL: Record<LiveAgentStage, string> = {
  idle: "Waiting…",
  running: "Agent running",
  post_processing: "Stitching response",
  verifying: "Verifier reviewing memo",
  verifier_done: "Verifier complete",
  done: "Done",
  error: "Failed",
};

export function LiveAgentPanel({ trace, stage }: LiveAgentPanelProps) {
  if (trace.length === 0 && stage === "idle") return null;

  return (
    <div className="border-t border-border bg-card/40 px-4 py-3">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles className="size-3.5 text-primary" />
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Live agent activity
        </span>
        <span className="text-xs text-muted-foreground ml-auto">
          {STAGE_LABEL[stage]}
        </span>
      </div>
      <ol className="space-y-1 max-h-48 overflow-y-auto pr-1">
        {trace.map((e) => (
          <li
            key={e.tool_use_id}
            className="flex items-start gap-2 text-xs leading-tight"
          >
            <StatusIcon status={e.status} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="font-mono text-[10px] text-muted-foreground">
                  i{e.iteration}
                </span>
                <span className="font-medium truncate">{e.name}</span>
                {e.duration_ms != null && e.status !== "running" && (
                  <span className="text-[10px] text-muted-foreground">
                    {e.duration_ms}ms
                  </span>
                )}
              </div>
              {e.output_summary && (
                <div className="text-[11px] text-muted-foreground truncate">
                  {e.output_summary}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function StatusIcon({ status }: { status: LiveAgentEvent["status"] }) {
  if (status === "running") {
    return <Loader2 className="size-3.5 mt-0.5 animate-spin text-primary shrink-0" />;
  }
  if (status === "error") {
    return <AlertCircle className="size-3.5 mt-0.5 text-destructive shrink-0" />;
  }
  return <CheckCircle2 className="size-3.5 mt-0.5 text-emerald-500 shrink-0" />;
}
