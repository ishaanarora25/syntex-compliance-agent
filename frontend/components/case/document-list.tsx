"use client";

import { FileText, Sparkles, Cpu } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { UploadedDocumentMeta } from "@/types/edd";

interface DocumentListProps {
  documents: UploadedDocumentMeta[];
}

const DOC_TYPE_LABELS: Record<string, string> = {
  articles_of_organization: "Articles of Organization",
  operating_agreement: "Operating Agreement",
  trust_agreement: "Trust Agreement",
  limited_partnership_agreement: "LP Agreement",
  commercial_register_extract: "Register Extract",
  certificate_of_incorporation: "Certificate of Incorporation",
  adverse_media_report: "Adverse Media Report",
  identity_document: "Government ID",
  other: "Other",
};

function prettyBytes(n: number): string {
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentList({ documents }: DocumentListProps) {
  if (!documents.length) {
    return (
      <div className="px-4 py-6 text-center text-xs text-muted-foreground">
        No documents uploaded yet.
      </div>
    );
  }

  return (
    <ul className="divide-y divide-border">
      {documents.map((d) => (
        <li key={d.doc_id} className="flex items-start gap-3 px-3 py-2.5">
          <FileText className="size-4 text-muted-foreground mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-foreground truncate" title={d.filename}>
              {d.label || d.filename}
            </div>
            <div className="flex items-center gap-1.5 mt-1 flex-wrap">
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                {DOC_TYPE_LABELS[d.doc_type] ?? d.doc_type}
              </Badge>
              <span
                className="inline-flex items-center gap-0.5 text-[10px] text-muted-foreground"
                title={`classifier: ${d.classifier_source}`}
              >
                {d.classifier_source === "claude" ? (
                  <Sparkles className="size-2.5" />
                ) : (
                  <Cpu className="size-2.5" />
                )}
                {(d.doc_type_confidence * 100).toFixed(0)}%
              </span>
              <span className="text-[10px] text-muted-foreground">
                · {d.page_count}p · {prettyBytes(d.size_bytes)}
              </span>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
