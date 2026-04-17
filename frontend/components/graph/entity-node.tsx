"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Building2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface EntityNodeData {
  label: string;
  entity_type: string;
  jurisdiction: string;
  is_ubo: boolean;
  risk_flags: string[];
  ofac_status?: string;
}

export function EntityNode({ data, selected }: NodeProps) {
  const d = data as unknown as EntityNodeData;
  const hasRisk = d.risk_flags?.length > 0;

  return (
    <div
      className={cn(
        "min-w-[160px] max-w-[200px] rounded-lg border bg-card px-3 py-2.5 shadow-sm text-xs",
        selected && "ring-2 ring-primary",
        hasRisk && "border-red-300 dark:border-red-800"
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-muted-foreground" />

      <div className="flex items-center gap-1.5 mb-1">
        <Building2 className="size-3 text-muted-foreground shrink-0" />
        <span className="font-medium text-foreground leading-tight truncate">{d.label}</span>
      </div>

      <div className="flex items-center gap-1 flex-wrap">
        <Badge variant="outline" className="text-[10px] h-4 px-1">{d.entity_type}</Badge>
        <span className="text-muted-foreground text-[10px] truncate">{d.jurisdiction?.split(",")[0]}</span>
      </div>

      {hasRisk && (
        <div className="mt-1 flex gap-1 flex-wrap">
          {d.risk_flags?.map((f) => (
            <Badge key={f} variant="danger" className="text-[10px] h-4 px-1">{f}</Badge>
          ))}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} className="!bg-muted-foreground" />
    </div>
  );
}
