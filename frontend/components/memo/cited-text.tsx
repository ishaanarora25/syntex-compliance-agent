"use client";

import { CitationTooltip } from "./citation-tooltip";
import type { Citation } from "@/types/edd";

interface CitedTextProps {
  content: string;
  citations: Citation[];
}

export function CitedText({ content, citations }: CitedTextProps) {
  // Split on [N] citation markers
  const parts = content.split(/(\[\d+\])/g);

  return (
    <span className="leading-relaxed">
      {parts.map((part, i) => {
        const match = part.match(/^\[(\d+)\]$/);
        if (match) {
          const n = parseInt(match[1], 10);
          const citation = citations[n - 1];
          if (citation) {
            return <CitationTooltip key={i} citation={citation} marker={n} />;
          }
          return <sup key={i} className="text-muted-foreground text-[10px]">[{n}]</sup>;
        }
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}
