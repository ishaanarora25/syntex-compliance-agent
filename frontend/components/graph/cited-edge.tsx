"use client";

import { getBezierPath, type EdgeProps } from "@xyflow/react";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";
import type { Citation } from "@/types/edd";

export interface CitedEdgeData {
  ownership_pct: number;
  citations: Citation[];
  edge_type: "direct" | "through_trust" | "look_through";
}

export function CitedEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps) {
  const d = data as unknown as CitedEdgeData;
  const isLookThrough = d?.edge_type === "look_through";
  const isThroughTrust = d?.edge_type === "through_trust";

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const strokeColor = isLookThrough
    ? "#94a3b8"
    : isThroughTrust
    ? "#f59e0b"
    : "#6366f1";

  const strokeDash = isLookThrough ? "5,5" : undefined;

  return (
    <>
      <path
        id={id}
        className="react-flow__edge-path"
        d={edgePath}
        stroke={strokeColor}
        strokeWidth={isLookThrough ? 1.5 : 2}
        strokeDasharray={strokeDash}
        fill="none"
        markerEnd="url(#arrowhead)"
      />
      {d?.ownership_pct != null && (
        <foreignObject
          width={60}
          height={24}
          x={labelX - 30}
          y={labelY - 12}
          requiredExtensions="http://www.w3.org/1999/xhtml"
        >
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center justify-center cursor-pointer">
                  <span
                    className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full border bg-white dark:bg-gray-900 shadow-sm select-none"
                    style={{ color: strokeColor, borderColor: strokeColor }}
                  >
                    {d.ownership_pct === 100
                      ? "100%"
                      : `${d.ownership_pct.toFixed(1)}%`}
                    {isLookThrough && " ↻"}
                  </span>
                </div>
              </TooltipTrigger>
              {d.citations?.length > 0 && (
                <TooltipContent
                  side="top"
                  className="max-w-xs bg-popover text-popover-foreground border border-border shadow-md p-3"
                >
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-foreground">
                      {isLookThrough ? "Trust look-through" : "Source citations"}
                    </p>
                    {d.citations.map((c, i) => (
                      <div key={i} className="space-y-0.5">
                        <p className="text-xs font-medium text-foreground">{c.doc_label} — p.{c.page}</p>
                        <p className="text-[10px] text-muted-foreground font-mono leading-relaxed line-clamp-3">
                          "{c.excerpt}"
                        </p>
                      </div>
                    ))}
                  </div>
                </TooltipContent>
              )}
            </Tooltip>
          </TooltipProvider>
        </foreignObject>
      )}
    </>
  );
}
