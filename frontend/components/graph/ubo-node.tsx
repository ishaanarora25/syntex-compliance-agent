"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { User, AlertTriangle, AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface UboNodeData {
  label: string;
  entity_type: string;
  jurisdiction: string;
  is_ubo: boolean;
  risk_flags: string[];
  ofac_status?: string;
}

export function UboNode({ data, selected }: NodeProps) {
  const d = data as unknown as UboNodeData;
  const hasAdverseMedia = d.risk_flags?.includes("adverse_media");
  const hasOFACHit = d.ofac_status === "confirmed_hit";
  const hasOFACMatch = d.ofac_status === "potential_match";
  const isForeign = d.risk_flags?.includes("foreign_national");

  const borderColor = hasAdverseMedia || hasOFACHit
    ? "border-red-400 dark:border-red-600"
    : hasOFACMatch
    ? "border-amber-400 dark:border-amber-600"
    : "border-emerald-400 dark:border-emerald-600";

  const bgColor = hasAdverseMedia || hasOFACHit
    ? "bg-red-50 dark:bg-red-950/30"
    : hasOFACMatch
    ? "bg-amber-50 dark:bg-amber-950/30"
    : "bg-emerald-50 dark:bg-emerald-950/30";

  return (
    <div
      className={cn(
        "min-w-[180px] max-w-[220px] rounded-lg border-2 px-3 py-2.5 shadow-sm text-xs",
        borderColor,
        bgColor,
        selected && "ring-2 ring-primary"
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-muted-foreground" />

      <div className="flex items-center gap-1.5 mb-1.5">
        <User className="size-3.5 text-muted-foreground shrink-0" />
        <span className="font-semibold text-foreground leading-tight">{d.label}</span>
        {(hasAdverseMedia || hasOFACHit) && (
          <AlertTriangle className="size-3 text-red-500 shrink-0 ml-auto" />
        )}
        {hasOFACMatch && !hasAdverseMedia && (
          <AlertCircle className="size-3 text-amber-500 shrink-0 ml-auto" />
        )}
      </div>

      <div className="flex flex-wrap gap-1">
        <Badge variant="success" className="text-[10px] h-4 px-1">UBO</Badge>
        {isForeign && (
          <Badge variant="warning" className="text-[10px] h-4 px-1">Foreign</Badge>
        )}
        {hasAdverseMedia && (
          <Badge variant="danger" className="text-[10px] h-4 px-1">Adverse Media</Badge>
        )}
        {hasOFACHit && (
          <Badge variant="danger" className="text-[10px] h-4 px-1">OFAC Hit</Badge>
        )}
        {hasOFACMatch && (
          <Badge variant="warning" className="text-[10px] h-4 px-1">OFAC Match?</Badge>
        )}
      </div>

      <p className="text-muted-foreground text-[10px] mt-1 truncate">
        {d.jurisdiction?.split(",")[0]}
      </p>
    </div>
  );
}
