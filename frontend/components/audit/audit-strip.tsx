"use client";

import { ClipboardCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { AuditEntry } from "@/types/edd";

interface AuditStripProps {
  entries: AuditEntry[];
}

const RISK_BADGE: Record<string, "success" | "warning" | "danger"> = {
  low: "success",
  medium: "warning",
  high: "danger",
};

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

export function AuditStrip({ entries }: AuditStripProps) {
  return (
    <div className="h-10 border-t border-border bg-muted/30 flex items-center px-4 gap-3 overflow-x-auto shrink-0">
      <div className="flex items-center gap-1.5 shrink-0">
        <ClipboardCheck className="size-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">Audit Log</span>
      </div>

      <div className="w-px h-4 bg-border shrink-0" />

      {entries.length === 0 ? (
        <span className="text-xs text-muted-foreground/60 italic">No approvals yet</span>
      ) : (
        <div className="flex items-center gap-3 overflow-x-auto">
          {entries.map((entry) => (
            <div
              key={entry.entry_id}
              className="flex items-center gap-2 shrink-0 animate-in slide-in-from-left-2"
            >
              <span className="font-mono text-[10px] text-muted-foreground">{formatTime(entry.timestamp)}</span>
              <Badge variant={RISK_BADGE[entry.risk_level] ?? "secondary"} className="text-[10px] h-5">
                {entry.event}
              </Badge>
              <span className="text-xs text-foreground/80">{entry.fixture_label}</span>
              <span className="text-[10px] text-muted-foreground">by {entry.approved_by}</span>
              <span className="text-[10px] text-muted-foreground italic">— {entry.conclusion}</span>
              <div className="w-px h-3 bg-border" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
