"use client";

import { useEffect, useRef } from "react";
import {
  CheckCircle2,
  Loader2,
  AlertCircle,
  Sparkles,
  GitBranch,
  CheckCheck,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { MemoSection } from "@/components/memo/memo-section";
import { cn } from "@/lib/utils";
import type {
  AnalyzeResponse,
  GraphNode,
  GraphEdge,
  ResolvedUBO,
} from "@/types/edd";
import type {
  ChatEvent,
  LiveAgentEvent,
  LiveAgentStage,
} from "@/components/scenario/use-scenario";

interface AnalysisChatViewProps {
  chatEvents: ChatEvent[];
  liveStage: LiveAgentStage;
  analysisResult: AnalyzeResponse | null;
  isAnalyzing: boolean;
  applicantName?: string;
  documentCount?: number;
  onUpdateSection: (sectionId: string, content: string) => void;
}

const STAGE_LABELS: Partial<Record<LiveAgentStage, string>> = {
  running: "Analyzing",
  post_processing: "Building checklist",
  verifying: "Verifying memo",
  verifier_done: "Verifying memo",
  done: "Complete",
  error: "Failed",
};

export function AnalysisChatView({
  chatEvents,
  liveStage,
  analysisResult,
  isAnalyzing,
  applicantName,
  documentCount,
  onUpdateSection,
}: AnalysisChatViewProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatEvents.length, !!analysisResult]);

  return (
    <div className="flex flex-col h-full">
      <ChatHeader stage={liveStage} applicantName={applicantName} documentCount={documentCount} />

      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="px-6 py-5 max-w-3xl mx-auto w-full space-y-3">

          {chatEvents.length === 0 && isAnalyzing && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
              <Loader2 className="size-4 animate-spin shrink-0" />
              Connecting to analysis stream…
            </div>
          )}

          {chatEvents.map((item, i) =>
            item.kind === "text" ? (
              <NarrativeBlock key={`t-${i}`} text={item.event.text} />
            ) : (
              <ToolIndicator key={`c-${i}`} event={item.event} />
            )
          )}

          {liveStage === "post_processing" && (
            <PhaseLabel label="Building ownership graph and checklist…" />
          )}
          {(liveStage === "verifying" || liveStage === "verifier_done") && (
            <PhaseLabel label="Verifier reviewing memo for gaps…" />
          )}

          {analysisResult && (
            <FinalOutput
              result={analysisResult}
              onUpdateSection={onUpdateSection}
            />
          )}

          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────────

function ChatHeader({
  stage,
  applicantName,
  documentCount,
}: {
  stage: LiveAgentStage;
  applicantName?: string;
  documentCount?: number;
}) {
  const label = STAGE_LABELS[stage];
  const isDone = stage === "done";
  const isError = stage === "error";
  const isActive =
    stage === "running" ||
    stage === "post_processing" ||
    stage === "verifying" ||
    stage === "verifier_done";

  return (
    <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-card/50 shrink-0">
      <div className="flex items-center gap-2">
        <Sparkles className="size-3.5 text-primary shrink-0" />
        <span className="text-xs font-semibold text-foreground">
          Agent Analysis
        </span>
        {applicantName && (
          <>
            <span className="text-xs text-muted-foreground">·</span>
            <span className="text-xs text-muted-foreground truncate max-w-[200px]">
              {applicantName}
              {documentCount != null && documentCount > 0
                ? ` · ${documentCount} doc${documentCount !== 1 ? "s" : ""}`
                : ""}
            </span>
          </>
        )}
      </div>
      {label && (
        <div className="flex items-center gap-1.5">
          {isActive && (
            <span className="relative flex size-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
              <span className="relative inline-flex rounded-full size-2 bg-amber-500" />
            </span>
          )}
          {isDone && (
            <span className="inline-flex rounded-full size-2 bg-emerald-500" />
          )}
          {isError && (
            <span className="inline-flex rounded-full size-2 bg-destructive" />
          )}
          <span
            className={cn(
              "text-xs",
              isDone && "text-emerald-600 dark:text-emerald-400",
              isError && "text-destructive",
              isActive && "text-amber-600 dark:text-amber-400",
              !isDone && !isError && !isActive && "text-muted-foreground"
            )}
          >
            {label}
          </span>
        </div>
      )}
    </div>
  );
}

function NarrativeBlock({ text }: { text: string }) {
  return (
    <div className="text-sm text-foreground/90 leading-relaxed prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-headings:mt-3 prose-headings:mb-1">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

function ToolIndicator({ event }: { event: LiveAgentEvent }) {
  return (
    <div className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground pl-1 py-0.5">
      <StatusIcon status={event.status} />
      <span className="text-muted-foreground/50">i{event.iteration}</span>
      <span className="text-muted-foreground/60">→</span>
      <span className="text-foreground/60">{event.name}</span>
      {event.duration_ms != null && event.status !== "running" && (
        <span className="text-muted-foreground/40">{event.duration_ms}ms</span>
      )}
    </div>
  );
}

function PhaseLabel({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground py-1">
      <Loader2 className="size-3 animate-spin shrink-0" />
      {label}
    </div>
  );
}

function StatusIcon({ status }: { status: LiveAgentEvent["status"] }) {
  if (status === "running") {
    return <Loader2 className="size-3 animate-spin text-primary/60 shrink-0" />;
  }
  if (status === "error") {
    return <AlertCircle className="size-3 text-destructive shrink-0" />;
  }
  return <CheckCircle2 className="size-3 text-emerald-500/70 shrink-0" />;
}

function FinalOutput({
  result,
  onUpdateSection,
}: {
  result: AnalyzeResponse;
  onUpdateSection: (sectionId: string, content: string) => void;
}) {
  const riskVariant =
    result.risk_level === "low"
      ? "success"
      : result.risk_level === "high"
      ? "destructive"
      : "warning";

  return (
    <div className="space-y-5 pt-2">
      <div className="flex items-center gap-3">
        <Separator className="flex-1" />
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground shrink-0">
          <CheckCheck className="size-3.5 text-emerald-500" />
          Analysis complete
        </div>
        <Separator className="flex-1" />
      </div>

      {/* Conclusion badge */}
      <div className="flex items-start gap-3 rounded-lg border border-border bg-card px-4 py-3">
        <Badge variant={riskVariant as "success" | "warning" | "destructive"} className="shrink-0 mt-0.5 uppercase text-[10px]">
          {result.risk_level} risk
        </Badge>
        <p className="text-sm text-foreground/80 leading-relaxed">
          {result.agent_work_product?.conclusion}
        </p>
      </div>

      {/* Ownership structure table */}
      {result.graph_nodes.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
            <GitBranch className="size-3.5 text-muted-foreground" />
            Ownership Structure
          </h3>
          <OwnershipTable
            nodes={result.graph_nodes}
            edges={result.graph_edges}
            ubos={result.resolved_ubos}
          />
        </div>
      )}

      {/* Justification sections */}
      {result.justification_sections.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-foreground">Intake Justification</h3>
          <div className="space-y-3">
            {result.justification_sections.map((section) => (
              <MemoSection
                key={section.section_id}
                section={section}
                onUpdate={(content) => onUpdateSection(section.section_id, content)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function OwnershipTable({
  nodes,
  edges,
  ubos,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  ubos: ResolvedUBO[];
}) {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const parentMap = new Map<
    string,
    { sourceLabel: string; pct: number; edgeType: string }[]
  >();
  for (const e of edges) {
    if (!parentMap.has(e.target)) parentMap.set(e.target, []);
    const srcLabel = nodeMap.get(e.source)?.label ?? e.source;
    parentMap
      .get(e.target)!
      .push({ sourceLabel: srcLabel, pct: e.ownership_pct, edgeType: e.edge_type });
  }
  const uboPcts = new Map(ubos.map((u) => [u.entity_id, u.ownership_pct]));

  const rows = nodes.map((n) => {
    const parents = parentMap.get(n.id) ?? [];
    const owners =
      parents.length === 0
        ? null
        : parents.map((p) => ({
            label: p.sourceLabel,
            pct: p.pct,
            lookThrough: p.edgeType === "look_through",
          }));
    const uboPct = uboPcts.has(n.id) ? uboPcts.get(n.id)! : null;
    return { node: n, owners, uboPct };
  });

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="border-b border-border bg-muted/40">
              <th className="px-3 py-2 text-left font-semibold text-muted-foreground whitespace-nowrap">Entity</th>
              <th className="px-3 py-2 text-left font-semibold text-muted-foreground whitespace-nowrap">Type</th>
              <th className="px-3 py-2 text-left font-semibold text-muted-foreground whitespace-nowrap">Jurisdiction</th>
              <th className="px-3 py-2 text-left font-semibold text-muted-foreground">Owner(s)</th>
              <th className="px-3 py-2 text-right font-semibold text-muted-foreground whitespace-nowrap">Eff. %</th>
              <th className="px-3 py-2 text-left font-semibold text-muted-foreground">Flags</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ node, owners, uboPct }, i) => (
              <tr
                key={node.id}
                className={cn(
                  "border-b border-border/50 last:border-0",
                  node.is_ubo && "bg-amber-50/30 dark:bg-amber-950/10"
                )}
              >
                <td className="px-3 py-2 font-medium text-foreground max-w-[160px]">
                  <span className={node.is_ubo ? "font-semibold" : undefined}>
                    {node.label}
                  </span>
                  {node.is_ubo && (
                    <span className="ml-1 text-[10px] font-semibold text-amber-600 dark:text-amber-400 whitespace-nowrap">
                      [UBO]
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-muted-foreground whitespace-nowrap capitalize">
                  {node.node_type}
                </td>
                <td className="px-3 py-2 text-muted-foreground max-w-[120px]">
                  {node.jurisdiction || "—"}
                </td>
                <td className="px-3 py-2 text-muted-foreground max-w-[180px]">
                  {owners === null ? (
                    <span className="text-muted-foreground/40">—</span>
                  ) : (
                    <div className="space-y-0.5">
                      {owners.map((o, j) => (
                        <div key={j}>
                          {o.label}
                          {o.pct > 0 && (
                            <span className="ml-1 text-foreground/60 whitespace-nowrap">
                              {o.pct.toFixed(1)}%
                            </span>
                          )}
                          {o.lookThrough && (
                            <span className="ml-1 text-[10px] text-muted-foreground/60 italic whitespace-nowrap">
                              look-through
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2 text-right whitespace-nowrap font-medium">
                  {uboPct !== null ? (
                    <span className={uboPct >= 25 ? "text-amber-600 dark:text-amber-400" : "text-foreground/70"}>
                      {uboPct.toFixed(1)}%
                    </span>
                  ) : (
                    <span className="text-muted-foreground/40">—</span>
                  )}
                </td>
                <td className="px-3 py-2 max-w-[140px]">
                  {node.risk_flags.length > 0 ? (
                    <div className="space-y-0.5">
                      {node.risk_flags.map((f, j) => (
                        <div key={j} className="text-amber-600 dark:text-amber-400 whitespace-nowrap">
                          ⚠ {f.replace(/_/g, " ")}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <span className="text-muted-foreground/40">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
