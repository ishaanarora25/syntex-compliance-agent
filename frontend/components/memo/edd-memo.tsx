"use client";

import { AlertTriangle, User, CheckCircle, AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { MemoSection } from "./memo-section";
import type { AnalyzeResponse, MemoSection as MemoSectionType } from "@/types/edd";

interface EddMemoProps {
  result: AnalyzeResponse;
  memoSections: MemoSectionType[];
  onUpdateSection: (sectionId: string, content: string) => void;
}

const OFAC_ICON = {
  clear: CheckCircle,
  potential_match: AlertCircle,
  confirmed_hit: AlertTriangle,
};

const OFAC_COLOR = {
  clear: "text-green-500",
  potential_match: "text-amber-500",
  confirmed_hit: "text-red-500",
};

export function EddMemo({ result, memoSections, onUpdateSection }: EddMemoProps) {
  const highRiskUBOs = result.resolved_ubos.filter((u) => u.risk_flags.length > 0);

  return (
    <div className="space-y-5">
      {/* Risk header */}
      <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/30 p-3 space-y-2">
        <div className="flex items-center gap-2">
          <AlertTriangle className="size-4 text-red-500 shrink-0" />
          <span className="text-sm font-semibold text-red-700 dark:text-red-400">
            Enhanced Due Diligence Required
          </span>
        </div>
        <div className="space-y-1.5">
          {highRiskUBOs.map((ubo) => {
            const OFACIcon = OFAC_ICON[ubo.ofac_result.status] ?? CheckCircle;
            const ofacColor = OFAC_COLOR[ubo.ofac_result.status] ?? "text-muted-foreground";
            return (
              <div key={ubo.entity_id} className="flex items-start gap-2 text-xs">
                <User className="size-3 text-muted-foreground shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <span className="font-medium text-foreground">{ubo.name}</span>
                  <span className="text-muted-foreground ml-1">({ubo.ownership_pct.toFixed(1)}%{ubo.ubo_by_control ? "*" : ""})</span>
                  <div className="flex gap-1 mt-0.5 flex-wrap">
                    {ubo.risk_flags.map((f) => (
                      <Badge key={f} variant="danger" className="text-[10px] h-4 px-1">{f.replace("_", " ")}</Badge>
                    ))}
                    {ubo.ofac_result.status !== "clear" && (
                      <span className={`text-[10px] flex items-center gap-0.5 ${ofacColor}`}>
                        <OFACIcon className="size-3" />
                        OFAC: {ubo.ofac_result.status.replace("_", " ")}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        <p className="text-[10px] text-red-600/70 dark:text-red-400/70">
          * UBO by trustee control authority. This memo is a DRAFT — analyst review and approval required.
        </p>
      </div>

      <Separator />

      {/* Memo sections */}
      {memoSections.map((section) => (
        <div key={section.section_id}>
          <MemoSection
            section={section}
            onUpdate={(content) => onUpdateSection(section.section_id, content)}
          />
          <Separator className="mt-4" />
        </div>
      ))}
    </div>
  );
}
