"use client";

import { useEffect, useRef, useState } from "react";
import {
  Plus,
  FolderOpen,
  Settings,
  X,
  Bot,
  ChevronRight,
  GitMerge,
  ShieldCheck,
  Building2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import type { CaseSummary, FixtureMeta } from "@/types/edd";

interface CaseSidebarProps {
  cases: CaseSummary[];
  fixtures: FixtureMeta[];
  activeCaseId: string | null;
  activeFixtureId: string | null;
  isBusy: boolean;
  useAgentLoop: boolean;
  onToggleAgentLoop: (next: boolean) => void;
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

function NavRow({
  icon: Icon,
  label,
  description,
}: {
  icon: React.ElementType;
  label: string;
  description: string;
}) {
  return (
    <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-muted/60 transition-colors text-left group">
      <div className="flex size-7 items-center justify-center rounded-md bg-muted border border-border shrink-0">
        <Icon className="size-3.5 text-muted-foreground" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium text-foreground leading-tight">{label}</div>
        <div className="text-[10px] text-muted-foreground mt-0.5 leading-tight">{description}</div>
      </div>
      <ChevronRight className="size-3.5 text-muted-foreground/50 group-hover:text-muted-foreground transition-colors shrink-0" />
    </button>
  );
}

export function CaseSidebar({
  cases,
  fixtures,
  activeCaseId,
  activeFixtureId,
  isBusy,
  useAgentLoop,
  onToggleAgentLoop,
  onCreateCase,
  onSelectCase,
  onSelectFixture,
}: CaseSidebarProps) {
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);

  const settingsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!settingsOpen) return;
    function handleClick(e: MouseEvent) {
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setSettingsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [settingsOpen]);

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
      </div>

      {/* Settings trigger */}
      <div className="relative border-t border-border" ref={settingsRef}>
        {settingsOpen && (
          <div className="absolute bottom-full left-0 right-0 mb-1 mx-2 bg-card border border-border rounded-xl shadow-lg z-50 overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2.5 border-b border-border">
              <span className="text-xs font-semibold text-foreground">Settings</span>
              <button
                onClick={() => setSettingsOpen(false)}
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                <X className="size-3.5" />
              </button>
            </div>

            <div className="px-2 py-2 flex flex-col gap-0.5">
              {/* Analysis engine — only section with an inline control */}
              <div className="px-3 py-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bot className="size-3.5 text-muted-foreground" />
                  <div>
                    <div className="text-xs font-medium text-foreground leading-tight">Analysis engine</div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">
                      {useAgentLoop ? "Opus 4.7 + tools" : "Legacy pipeline"}
                    </div>
                  </div>
                </div>
                <button
                  role="switch"
                  aria-checked={useAgentLoop}
                  disabled={isBusy}
                  onClick={() => onToggleAgentLoop(!useAgentLoop)}
                  className={cn(
                    "relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors",
                    useAgentLoop ? "bg-primary" : "bg-muted",
                    isBusy && "opacity-50 cursor-not-allowed"
                  )}
                >
                  <span
                    className={cn(
                      "inline-block size-3 transform rounded-full bg-background shadow transition-transform",
                      useAgentLoop ? "translate-x-3.5" : "translate-x-0.5"
                    )}
                  />
                </button>
              </div>

              <Separator className="my-1" />

              <NavRow
                icon={GitMerge}
                label="Workflow"
                description="Approval chains, escalation, SLAs"
              />
              <NavRow
                icon={ShieldCheck}
                label="Compliance rules"
                description="Thresholds, screening, jurisdictions"
              />
              <NavRow
                icon={Building2}
                label="Organization"
                description="Team, branding, integrations"
              />
            </div>
          </div>
        )}

        <button
          onClick={() => setSettingsOpen((v) => !v)}
          className={cn(
            "w-full flex items-center gap-2 px-3 py-2.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors",
            settingsOpen && "bg-muted/40 text-foreground"
          )}
        >
          <Settings className="size-3.5 shrink-0" />
          <span className="font-medium">Settings</span>
        </button>
      </div>
    </aside>
  );
}
