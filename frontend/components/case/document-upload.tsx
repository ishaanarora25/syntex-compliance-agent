"use client";

import { useCallback, useRef, useState } from "react";
import { FileUp, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface DocumentUploadProps {
  onUpload: (files: File[]) => Promise<void>;
  isUploading: boolean;
  disabled?: boolean;
}

const ACCEPT = "application/pdf,.pdf";

export function DocumentUpload({ onUpload, isUploading, disabled }: DocumentUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const submit = useCallback(
    (files: FileList | File[]) => {
      const accepted: File[] = [];
      for (const f of Array.from(files)) {
        if (f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")) {
          accepted.push(f);
        }
      }
      if (accepted.length === 0) return;
      onUpload(accepted).catch(() => {
        /* caller surfaces error */
      });
    },
    [onUpload]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled && !isUploading) setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragging(false);
        if (disabled || isUploading) return;
        if (e.dataTransfer.files?.length) submit(e.dataTransfer.files);
      }}
      className={cn(
        "relative flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 transition-colors",
        isDragging
          ? "border-primary bg-primary/5"
          : "border-border bg-muted/20 hover:bg-muted/40",
        (disabled || isUploading) && "opacity-60 cursor-not-allowed"
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        multiple
        className="hidden"
        onChange={(e) => {
          if (e.target.files?.length) submit(e.target.files);
          e.target.value = "";
        }}
      />

      {isUploading ? (
        <>
          <Loader2 className="size-7 text-primary animate-spin" />
          <p className="text-sm font-medium text-foreground">Extracting & classifying…</p>
          <p className="text-xs text-muted-foreground">
            Reading PDFs, identifying entities, and building the ownership graph.
          </p>
        </>
      ) : (
        <>
          <FileUp className="size-7 text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">Drop formation & KYC PDFs here</p>
          <p className="text-xs text-muted-foreground text-center max-w-md">
            Articles of organization, operating agreements, trust agreements, LP agreements,
            commercial register extracts, IDs, adverse-media reports.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled}
            onClick={() => inputRef.current?.click()}
            className="mt-2 gap-1.5"
          >
            <FileText className="size-3.5" />
            Browse files
          </Button>
        </>
      )}
    </div>
  );
}
