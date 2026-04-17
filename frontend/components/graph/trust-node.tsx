"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Shield } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface TrustNodeData {
  label: string;
  entity_type: string;
  jurisdiction: string;
  is_ubo: boolean;
  risk_flags: string[];
}

export function TrustNode({ data, selected }: NodeProps) {
  const d = data as unknown as TrustNodeData;
  const isIrrevocable = d.entity_type?.toLowerCase().includes("irrevocable");

  return (
    <div
      className={cn(
        "min-w-[160px] max-w-[200px] rounded-lg border-2 border-dashed bg-card px-3 py-2.5 shadow-sm text-xs",
        isIrrevocable ? "border-orange-300 dark:border-orange-700" : "border-blue-300 dark:border-blue-700",
        selected && "ring-2 ring-primary"
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-muted-foreground" />

      <div className="flex items-center gap-1.5 mb-1">
        <Shield className={cn("size-3 shrink-0", isIrrevocable ? "text-orange-500" : "text-blue-500")} />
        <span className="font-medium text-foreground leading-tight truncate">{d.label}</span>
      </div>

      <div className="flex items-center gap-1 flex-wrap">
        <Badge
          variant="outline"
          className={cn(
            "text-[10px] h-4 px-1",
            isIrrevocable ? "border-orange-300 text-orange-700" : "border-blue-300 text-blue-700"
          )}
        >
          {d.entity_type}
        </Badge>
        <span className="text-muted-foreground text-[10px]">Look-through →</span>
      </div>

      <Handle type="source" position={Position.Bottom} className="!bg-muted-foreground" />
    </div>
  );
}
