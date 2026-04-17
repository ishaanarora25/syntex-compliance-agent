import { Shield } from "lucide-react";

export function AppHeader() {
  return (
    <header className="sticky top-0 z-50 flex h-14 items-center gap-3 border-b border-border bg-card/80 backdrop-blur-sm px-6">
      <div className="flex items-center gap-2">
        <Shield className="size-5 text-primary" />
        <span className="font-semibold text-foreground tracking-tight">Syntex EDD</span>
        <span className="text-muted-foreground text-xs border-l border-border pl-3 ml-1">
          Enhanced Due Diligence — BSA Compliance
        </span>
      </div>
      <div className="ml-auto">
        <span className="text-xs text-muted-foreground bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400 px-2 py-0.5 rounded-full font-medium">
          DEMO — All outputs require analyst review
        </span>
      </div>
    </header>
  );
}
