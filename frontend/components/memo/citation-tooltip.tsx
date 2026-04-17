"use client";

import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";
import type { Citation } from "@/types/edd";

interface CitationTooltipProps {
  citation: Citation;
  marker: number;
}

export function CitationTooltip({ citation, marker }: CitationTooltipProps) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <sup
            className="cursor-pointer text-primary hover:text-primary/70 transition-colors font-semibold text-[10px] ml-0.5"
            aria-label={`Citation ${marker}: ${citation.doc_label}, page ${citation.page}`}
          >
            [{marker}]
          </sup>
        </TooltipTrigger>
        <TooltipContent
          side="top"
          className="max-w-sm bg-popover text-popover-foreground border border-border shadow-lg p-3 z-50"
        >
          <div className="space-y-2">
            <div className="flex items-baseline justify-between gap-3">
              <p className="text-xs font-semibold text-foreground leading-tight">
                {citation.doc_label}
              </p>
              <p className="text-xs text-muted-foreground whitespace-nowrap">
                Page {citation.page}
              </p>
            </div>
            {citation.excerpt && (
              <pre className="font-mono text-[10px] text-muted-foreground bg-muted/50 rounded p-2 whitespace-pre-wrap leading-relaxed max-h-24 overflow-y-auto">
                "{citation.excerpt}"
              </pre>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
