"use client";

import { CheckCircle2, AlertTriangle, Circle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { CDDChecklist as CDDChecklistT } from "@/types/edd";

interface CDDChecklistProps {
  checklist: CDDChecklistT | null;
}

export function CDDChecklist({ checklist }: CDDChecklistProps) {
  if (!checklist) {
    return (
      <div className="px-4 py-6 text-center text-xs text-muted-foreground">
        Upload documents and run analysis to generate the CDD checklist.
      </div>
    );
  }

  if (!checklist.items.length) {
    return (
      <div className="px-4 py-6 text-center text-xs text-muted-foreground">
        No CDD requirements triggered for this entity structure.
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-muted/30">
        <Badge variant="success" className="text-[10px]">
          {checklist.satisfied_count} provided
        </Badge>
        <Badge
          variant={checklist.missing_count === 0 ? "secondary" : "warning"}
          className="text-[10px]"
        >
          {checklist.missing_count} missing
        </Badge>
        {checklist.blocking_for_ubo_resolution && (
          <Badge variant="danger" className="text-[10px] ml-auto gap-1">
            <AlertTriangle className="size-2.5" />
            Blocks UBO finalization
          </Badge>
        )}
      </div>

      <ul className="divide-y divide-border">
        {checklist.items.map((item) => (
          <li key={item.requirement_id} className="flex items-start gap-2.5 px-4 py-2.5">
            {item.status === "provided" ? (
              <CheckCircle2 className="size-4 text-green-600 dark:text-green-500 mt-0.5 shrink-0" />
            ) : item.status === "missing" ? (
              <Circle className="size-4 text-amber-600 dark:text-amber-500 mt-0.5 shrink-0" />
            ) : (
              <Circle className="size-4 text-muted-foreground mt-0.5 shrink-0" />
            )}
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-foreground">{item.label}</div>
              <div className="text-xs text-muted-foreground mt-0.5 leading-snug">
                {item.rationale}
              </div>
              {item.provided_by.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {item.provided_by.map((id) => (
                    <Badge key={id} variant="outline" className="text-[10px] font-mono">
                      {id}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
