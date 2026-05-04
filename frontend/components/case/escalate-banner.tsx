"use client";

import { AlertTriangle, ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { EscalationRecommendation } from "@/types/edd";

interface EscalateBannerProps {
  escalation: EscalationRecommendation;
  onView?: () => void;
}

function humanizeSignal(signal: string): string {
  return signal
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function EscalateBanner({ escalation, onView }: EscalateBannerProps) {
  if (!escalation.escalated) return null;

  return (
    <div className="border-b border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 px-4 py-3 space-y-2">
      <div className="flex items-start gap-2">
        <AlertTriangle className="size-4 text-amber-600 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">
              Escalate to {escalation.recommended_team || "compliance team"}
            </p>
            {onView && (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 text-xs text-amber-800 dark:text-amber-200 hover:bg-amber-100 dark:hover:bg-amber-900/40 gap-1"
                onClick={onView}
              >
                View justification
                <ArrowRight className="size-3" />
              </Button>
            )}
          </div>
          {escalation.reasons.length > 0 && (
            <p className="text-xs text-amber-800/90 dark:text-amber-200/90 leading-relaxed">
              {escalation.reasons[0]}
            </p>
          )}
          <div className="flex flex-wrap gap-1 pt-0.5">
            {escalation.complexity_signals.map((signal) => (
              <Badge
                key={signal}
                variant="outline"
                className="text-[10px] h-4 px-1.5 border-amber-400 text-amber-800 dark:text-amber-200 bg-amber-100/50 dark:bg-amber-900/30"
              >
                {humanizeSignal(signal)}
              </Badge>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
