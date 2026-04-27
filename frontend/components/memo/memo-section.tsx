"use client";

import { useState } from "react";
import { Pencil, Check } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { visit } from "unist-util-visit";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { CitationTooltip } from "./citation-tooltip";
import type { MemoSection as MemoSectionType } from "@/types/edd";
import type { Plugin } from "unified";
import type { Root, Text, Parent } from "mdast";

interface MemoSectionProps {
  section: MemoSectionType;
  onUpdate: (content: string) => void;
}

// Remark plugin: splits [N] citation markers in text nodes into custom cite
// nodes so react-markdown can hand them to CitationTooltip.
function remarkCitations(): Plugin<[], Root> {
  return () => (tree: Root) => {
    visit(tree, "text", (node: Text, index, parent: Parent | null) => {
      if (!parent || index === undefined) return;
      if (!node.value.includes("[")) return;

      const parts = node.value.split(/(\[\d+\])/g);
      if (parts.length <= 1) return;

      const newNodes = parts
        .filter((p) => p !== "")
        .map((part) => {
          const m = part.match(/^\[(\d+)\]$/);
          if (m) {
            // Emit a raw HTML node that carries the cite index as an attribute
            return {
              type: "html" as const,
              value: `<cite data-n="${m[1]}"></cite>`,
            };
          }
          return { type: "text" as const, value: part };
        });

      parent.children.splice(index, 1, ...newNodes);
      return index + newNodes.length;
    });
  };
}

interface MarkdownMemoProps {
  content: string;
  citations: MemoSectionType["citations"];
}

function MarkdownMemo({ content, citations }: MarkdownMemoProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkCitations()]}
      rehypePlugins={[rehypeRaw]}
      components={{
        // Headings
        h1: ({ children }) => (
          <h1 className="text-base font-bold text-foreground mt-4 mb-1.5 first:mt-0">
            {children}
          </h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-sm font-semibold text-foreground mt-4 mb-1.5 first:mt-0 border-b border-border pb-1">
            {children}
          </h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-sm font-semibold text-foreground mt-3 mb-1 first:mt-0">
            {children}
          </h3>
        ),
        // Paragraphs
        p: ({ children }) => (
          <p className="text-sm text-foreground/90 leading-relaxed mb-3 last:mb-0">
            {children}
          </p>
        ),
        // Lists
        ul: ({ children }) => (
          <ul className="list-disc list-outside pl-5 mb-3 space-y-1 text-sm text-foreground/90 leading-relaxed">
            {children}
          </ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal list-outside pl-5 mb-3 space-y-1 text-sm text-foreground/90 leading-relaxed">
            {children}
          </ol>
        ),
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        // Inline
        strong: ({ children }) => (
          <strong className="font-semibold text-foreground">{children}</strong>
        ),
        em: ({ children }) => <em className="italic">{children}</em>,
        code: ({ children }) => (
          <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
            {children}
          </code>
        ),
        // Blockquote (used for highlighted findings)
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-primary pl-3 my-3 text-sm text-muted-foreground italic">
            {children}
          </blockquote>
        ),
        // Tables (GFM)
        table: ({ children }) => (
          <div className="overflow-x-auto my-3">
            <table className="w-full text-xs border-collapse">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-muted/50">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="border border-border px-2 py-1 text-left font-semibold">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="border border-border px-2 py-1">{children}</td>
        ),
        // Citation markers emitted by the remark plugin as raw HTML <cite>
        cite: (props) => {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const raw = (props as any).node?.properties?.dataN;
          const n = raw ? parseInt(String(raw), 10) : NaN;
          const citation = !isNaN(n) ? citations[n - 1] : undefined;
          if (citation) {
            return <CitationTooltip citation={citation} marker={n} />;
          }
          return <sup className="text-[10px] text-muted-foreground">[{n}]</sup>;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export function MemoSection({ section, onUpdate }: MemoSectionProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(section.content);

  const handleSave = () => {
    onUpdate(editValue);
    setIsEditing(false);
  };

  const handleEdit = () => {
    setEditValue(section.content);
    setIsEditing(true);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">{section.title}</h3>
        {!isEditing ? (
          <Button variant="ghost" size="icon" className="size-6 shrink-0" onClick={handleEdit}>
            <Pencil className="size-3" />
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            className="size-6 shrink-0 text-green-600"
            onClick={handleSave}
          >
            <Check className="size-3" />
          </Button>
        )}
      </div>

      {isEditing ? (
        <Textarea
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          className="text-sm min-h-[120px] font-mono text-xs leading-relaxed"
          autoFocus
        />
      ) : (
        <div className="prose-none">
          <MarkdownMemo content={section.content} citations={section.citations} />
        </div>
      )}

      {section.citations.length > 0 && !isEditing && (
        <div className="mt-2 pt-2 border-t border-border/50">
          <p className="text-[10px] text-muted-foreground font-medium mb-1">
            Sources ({section.citations.length})
          </p>
          <div className="flex flex-wrap gap-1">
            {section.citations.map((c, i) => (
              <span
                key={i}
                className="text-[10px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded"
              >
                [{i + 1}] {c.doc_label}, p.{c.page}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
