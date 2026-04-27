"use client";

import { useState } from "react";
import {
  Plus,
  FolderOpen,
  FlaskConical,
  Loader2,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { CaseSummary, FixtureMeta } from "@/types/edd";

interface CaseSidebarProps {
  cases: CaseSummary[];
  fixtures: FixtureMeta[];
  activeCaseId: string | null;
  activeFixtureId: string | null;
  isBusy: boolean;
  onCreateCase: (name: string) => Promise<void>;
  onSelectCase: (caseId: string) => void;
  onSelectFixture: (fixtureId: string) => void;
}

const STATUS_LABELS: Record<CaseSummary["status"], string> = {
  awaiting_documents: "Awaiting docs",
  ready_to_analyze: "Ready to analyze",
  analyzing: "Analyzing",
  analyzed: "Analyzed",
  approved: "Approved",
};

const STATUS_VARIANT: Record<CaseSummary["status"], "secondary" | "warning" | "success"> = {
  awaiting_documents: "warning",
  ready_to_analyze: "secondary",
  analyzing: "secondary",
  analyzed: "success",
  approved: "success",
};

export function CaseSidebar({
  cases,
  fixtures,
  activeCaseId,
  activeFixtureId,
  isBusy,
  onCreateCase,
  onSelectCase,
  onSelectFixture,
}: CaseSidebarProps) {
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [showFixtures, setShowFixtures] = useState(true);

  const submitNew = async () => {
    const name = newName.trim() || "Untitled applicant";
    setCreating(false);
    setNewName("");
    await onCreateCase(name);
  };

  return (
    <aside className="flex flex-col h-full bg-card/30 border-r border-border w-64 shrink-0">
      <div className="px-3 py-3 border-b border-border">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Cases
          </span>
          <Button
            size="sm"
            variant="default"
            className="h-7 px-2.5 text-xs gap-1"
            onClick={() => setCreating(true)}
            disabled={isBusy}
          >
            <Plus className="size-3" />
            New case
          </Button>
        </div>

        {creating && (
          <div className="flex flex-col gap-1.5">
            <input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitNew();
                if (e.key === "Escape") {
                  setCreating(false);
                  setNewName("");
                }
              }}
              placeholder="Applicant or entity name"
              className="w-full rounded-md border border-border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <div className="flex gap-1">
              <Button size="sm" className="h-6 text-xs flex-1" onClick={submitNew}>
                Create
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-6 text-xs"
                onClick={() => {
                  setCreating(false);
                  setNewName("");
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {cases.length === 0 && !creating && (
          <div className="px-3 py-4 text-xs text-muted-foreground">
            No cases yet. Click <span className="font-medium">New</span> to start.
          </div>
        )}

        {cases.map((c) => (
          <button
            key={c.case_id}
            onClick={() => onSelectCase(c.case_id)}
            className={cn(
              "w-full flex items-start gap-2 px-3 py-2 text-left border-b border-border/50 hover:bg-muted/50 transition-colors",
              activeCaseId === c.case_id && "bg-primary/5 border-l-2 border-l-primary"
            )}
          >
            <FolderOpen className="size-3.5 text-muted-foreground mt-0.5 shrink-0" />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium truncate">{c.name}</div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <Badge variant={STATUS_VARIANT[c.status]} className="text-[9px] px-1 py-0">
                  {STATUS_LABELS[c.status]}
                </Badge>
                <span className="text-[10px] text-muted-foreground">
                  {c.document_count} doc{c.document_count !== 1 ? "s" : ""}
                </span>
              </div>
            </div>
          </button>
        ))}

        <div className="px-3 pt-3 pb-1">
          <button
            className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground"
            onClick={() => setShowFixtures((v) => !v)}
          >
            {showFixtures ? (
              <ChevronDown className="size-3" />
            ) : (
              <ChevronRight className="size-3" />
            )}
            <FlaskConical className="size-3" />
            Demo Scenarios
          </button>
        </div>

        {showFixtures &&
          fixtures.map((f) => (
            <button
              key={f.fixture_id}
              onClick={() => onSelectFixture(f.fixture_id)}
              className={cn(
                "w-full flex items-start gap-2 px-3 py-1.5 text-left hover:bg-muted/50 transition-colors",
                activeFixtureId === f.fixture_id && "bg-primary/5 border-l-2 border-l-primary"
              )}
              disabled={isBusy}
            >
              <FlaskConical className="size-3.5 text-muted-foreground mt-0.5 shrink-0" />
              <div className="min-w-0">
                <div className="text-xs font-medium truncate">{f.label}</div>
                <div className="text-[10px] text-muted-foreground truncate">
                  {f.scenario}
                </div>
              </div>
            </button>
          ))}
      </div>

      {isBusy && (
        <div className="border-t border-border px-3 py-2 flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" />
          Working…
        </div>
      )}
    </aside>
  );
}
