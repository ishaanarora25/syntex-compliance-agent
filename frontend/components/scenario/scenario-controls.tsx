"use client";

import { Loader2, ChevronDown, FlaskConical } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface ScenarioControlsProps {
  isLoading: boolean;
  activeFixtureId: string | null;
  riskLevel: string | null;
  onLoadScenario: (fixtureId: string) => void;
}

const RISK_BADGE: Record<string, "success" | "warning" | "danger"> = {
  low: "success",
  medium: "warning",
  high: "danger",
};

const RISK_LABELS: Record<string, string> = {
  low: "Low Risk",
  medium: "Medium Risk",
  high: "High Risk — EDD Required",
};

export function ScenarioControls({
  isLoading,
  activeFixtureId,
  riskLevel,
  onLoadScenario,
}: ScenarioControlsProps) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <span className="text-sm font-medium text-muted-foreground mr-1">Load Scenario:</span>

      <Button
        variant={activeFixtureId === "fixture_a" ? "default" : "outline"}
        size="sm"
        disabled={isLoading}
        onClick={() => onLoadScenario("fixture_a")}
      >
        {isLoading && activeFixtureId === null ? (
          <Loader2 className="animate-spin" />
        ) : null}
        Scenario A — Clean UBO
      </Button>

      <Button
        variant={activeFixtureId === "fixture_b" ? "default" : "outline"}
        size="sm"
        disabled={isLoading}
        onClick={() => onLoadScenario("fixture_b")}
      >
        Scenario B — EDD + Adverse Media
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" disabled={isLoading}>
            <FlaskConical className="size-3.5" />
            Stress Tests
            <ChevronDown className="size-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuLabel>Stress Test Fixtures</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => onLoadScenario("fixture_c")}>
            <span className="font-medium">Fixture C</span>
            <span className="text-muted-foreground text-xs ml-2">3-Level + GmbH + Trust</span>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => onLoadScenario("fixture_d")}>
            <span className="font-medium">Fixture D</span>
            <span className="text-muted-foreground text-xs ml-2">Joint Revocable + Cayman</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {isLoading && (
        <span className="flex items-center gap-1.5 text-sm text-muted-foreground ml-2">
          <Loader2 className="size-3.5 animate-spin" />
          Analyzing documents…
        </span>
      )}

      {!isLoading && riskLevel && (
        <Badge variant={RISK_BADGE[riskLevel] ?? "secondary"} className="ml-2">
          {RISK_LABELS[riskLevel] ?? riskLevel}
        </Badge>
      )}
    </div>
  );
}
