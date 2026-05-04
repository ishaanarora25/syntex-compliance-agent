import { ShieldCheck } from "lucide-react";

export function AppHeader() {
  return (
    <header className="sticky top-0 z-50 flex h-14 items-center gap-3 border-b border-border bg-card/80 backdrop-blur-sm px-6">
      <div className="flex items-center gap-2">
        <ShieldCheck className="size-5 text-primary" />
        <span className="font-semibold text-foreground tracking-tight">Syntex BSA Copilot</span>
        <span className="text-muted-foreground text-xs border-l border-border pl-3 ml-1">
          AI analyst for BSA/AML onboarding, UBO resolution & EDD
        </span>
      </div>
    </header>
  );
}
