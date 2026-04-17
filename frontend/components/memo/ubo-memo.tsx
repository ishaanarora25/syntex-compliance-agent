"use client";

import { User, CheckCircle, AlertCircle, AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { MemoSection } from "./memo-section";
import type { AnalyzeResponse, MemoSection as MemoSectionType } from "@/types/edd";

interface UboMemoProps {
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

export function UboMemo({ result, memoSections, onUpdateSection }: UboMemoProps) {
  return (
    <div className="space-y-5">
      {/* UBO Table */}
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-2">
          Resolved Beneficial Owners ({result.resolved_ubos.length})
        </h3>
        <div className="space-y-2">
          {result.resolved_ubos.map((ubo) => {
            const OFACIcon = OFAC_ICON[ubo.ofac_result.status] ?? CheckCircle;
            const ofacColor = OFAC_COLOR[ubo.ofac_result.status] ?? "text-muted-foreground";

            return (
              <div
                key={ubo.entity_id}
                className="rounded-lg border border-border bg-card p-3 text-xs space-y-1.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <User className="size-3.5 text-muted-foreground shrink-0" />
                    <span className="font-semibold text-foreground">{ubo.name}</span>
                    <Badge variant="outline" className="text-[10px] h-4">{ubo.nationality}</Badge>
                  </div>
                  <span className="font-mono text-foreground">
                    {ubo.ubo_by_control
                      ? <span className="text-orange-600 font-semibold">Control</span>
                      : `${ubo.ownership_pct.toFixed(1)}%`}
                  </span>
                </div>

                <div className="flex items-center gap-3 text-muted-foreground">
                  <div className="flex items-center gap-1">
                    <OFACIcon className={`size-3 ${ofacColor}`} />
                    <span className={`text-[10px] ${ofacColor} font-medium`}>
                      OFAC: {ubo.ofac_result.status.replace("_", " ")}
                    </span>
                  </div>
                  {ubo.risk_flags.filter(f => f !== "foreign_national").map((f) => (
                    <Badge key={f} variant="danger" className="text-[10px] h-4 px-1">{f}</Badge>
                  ))}
                </div>

                {ubo.ofac_result.status !== "clear" && ubo.ofac_result.remarks && (
                  <p className="text-[10px] text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded px-2 py-1 leading-relaxed">
                    {ubo.ofac_result.remarks}
                  </p>
                )}
              </div>
            );
          })}
        </div>
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
