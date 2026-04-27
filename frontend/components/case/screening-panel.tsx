"use client";

import { ExternalLink, ShieldCheck, ShieldAlert, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type {
  AdverseMediaResult,
  OFACResult,
  PEPResult,
  ResolvedUBO,
} from "@/types/edd";

interface ScreeningPanelProps {
  ubos: ResolvedUBO[];
}

type Variant = "success" | "warning" | "danger" | "secondary";

const STATUS_VARIANT: Record<string, Variant> = {
  clear: "success",
  potential_match: "warning",
  confirmed_hit: "danger",
  confirmed_pep: "danger",
};

const STATUS_LABEL: Record<string, string> = {
  clear: "Clear",
  potential_match: "Potential match",
  confirmed_hit: "Confirmed hit",
  confirmed_pep: "Confirmed PEP",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={STATUS_VARIANT[status] ?? "secondary"} className="text-[10px]">
      {STATUS_LABEL[status] ?? status}
    </Badge>
  );
}

function OfacCard({ r }: { r: OFACResult }) {
  return (
    <div className="rounded-md border border-border bg-card/30 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          OFAC / SDN
        </span>
        <StatusBadge status={r.status} />
      </div>
      {r.status !== "clear" && (
        <div className="mt-1.5 space-y-0.5 text-xs">
          {r.sdn_name && (
            <div>
              <span className="text-muted-foreground">Matched: </span>
              <span className="font-medium">{r.sdn_name}</span>
            </div>
          )}
          {r.program && (
            <div>
              <span className="text-muted-foreground">Program: </span>
              {r.program}
            </div>
          )}
          {typeof r.match_score === "number" && (
            <div>
              <span className="text-muted-foreground">Score: </span>
              {(r.match_score * 100).toFixed(0)}%
            </div>
          )}
          {r.remarks && (
            <div className="text-muted-foreground italic">{r.remarks}</div>
          )}
        </div>
      )}
    </div>
  );
}

function PepCard({ r }: { r: PEPResult }) {
  return (
    <div className="rounded-md border border-border bg-card/30 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          PEP
        </span>
        <StatusBadge status={r.status} />
      </div>
      {r.status !== "clear" && (
        <div className="mt-1.5 space-y-0.5 text-xs">
          {r.role && (
            <div>
              <span className="text-muted-foreground">Role: </span>
              {r.role}
            </div>
          )}
          {r.country && (
            <div>
              <span className="text-muted-foreground">Country: </span>
              {r.country}
            </div>
          )}
          {r.category && (
            <div>
              <span className="text-muted-foreground">Category: </span>
              {r.category.replace(/_/g, " ")}
            </div>
          )}
          {r.source && (
            <div className="text-muted-foreground">Source: {r.source}</div>
          )}
          {r.remarks && (
            <div className="text-muted-foreground italic">{r.remarks}</div>
          )}
        </div>
      )}
    </div>
  );
}

function AdverseMediaCard({ r }: { r: AdverseMediaResult }) {
  return (
    <div className="rounded-md border border-border bg-card/30 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          Adverse Media
        </span>
        <StatusBadge status={r.status} />
      </div>
      {r.status !== "clear" && (
        <div className="mt-1.5 space-y-1.5 text-xs">
          {r.categories.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {r.categories.map((c) => (
                <Badge key={c} variant="outline" className="text-[10px]">
                  {c.replace(/_/g, " ")}
                </Badge>
              ))}
              {r.severity && (
                <Badge
                  variant={r.severity === "high" ? "danger" : "warning"}
                  className="text-[10px]"
                >
                  severity: {r.severity}
                </Badge>
              )}
            </div>
          )}
          {r.articles.length > 0 && (
            <ul className="space-y-1">
              {r.articles.map((a, idx) => (
                <li key={idx} className="flex items-start gap-1.5">
                  <ExternalLink className="size-3 text-muted-foreground mt-0.5 shrink-0" />
                  <div className="min-w-0">
                    <div className="font-medium truncate">{a.headline}</div>
                    <div className="text-muted-foreground">
                      {a.source} · {a.date}
                      {a.disposition ? ` · ${a.disposition}` : ""}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {r.remarks && (
            <div className="text-muted-foreground italic">{r.remarks}</div>
          )}
        </div>
      )}
    </div>
  );
}

export function ScreeningPanel({ ubos }: ScreeningPanelProps) {
  if (!ubos.length) {
    return (
      <div className="px-4 py-6 text-center text-xs text-muted-foreground">
        No resolved beneficial owners — run analysis to view screening results.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      {ubos.map((ubo) => {
        const anyHit =
          ubo.ofac_result.status !== "clear" ||
          ubo.pep_result.status !== "clear" ||
          ubo.adverse_media_result.status !== "clear";

        return (
          <div
            key={ubo.entity_id}
            className="rounded-lg border border-border bg-card/50"
          >
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border">
              {anyHit ? (
                <ShieldAlert className="size-4 text-amber-600 dark:text-amber-500" />
              ) : (
                <ShieldCheck className="size-4 text-green-600 dark:text-green-500" />
              )}
              <User className="size-3.5 text-muted-foreground" />
              <span className="font-medium text-sm">{ubo.name}</span>
              <span className="text-xs text-muted-foreground">
                · {ubo.ownership_pct.toFixed(1)}% ·{" "}
                {ubo.nationality || "unknown nationality"}
              </span>
              {ubo.ubo_by_control && (
                <Badge variant="secondary" className="text-[10px] ml-auto">
                  UBO by control
                </Badge>
              )}
            </div>
            <div className="grid gap-2 p-3">
              <OfacCard r={ubo.ofac_result} />
              <PepCard r={ubo.pep_result} />
              <AdverseMediaCard r={ubo.adverse_media_result} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
