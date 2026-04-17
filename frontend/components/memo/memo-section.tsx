"use client";

import { useState } from "react";
import { Pencil, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { CitedText } from "./cited-text";
import type { MemoSection as MemoSectionType } from "@/types/edd";

interface MemoSectionProps {
  section: MemoSectionType;
  onUpdate: (content: string) => void;
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
          <Button variant="ghost" size="icon" className="size-6 shrink-0 text-green-600" onClick={handleSave}>
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
        <div className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
          <CitedText content={section.content} citations={section.citations} />
        </div>
      )}

      {section.citations.length > 0 && !isEditing && (
        <div className="mt-2 pt-2 border-t border-border/50">
          <p className="text-[10px] text-muted-foreground font-medium mb-1">
            Sources ({section.citations.length})
          </p>
          <div className="flex flex-wrap gap-1">
            {section.citations.map((c, i) => (
              <span key={i} className="text-[10px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">
                [{i + 1}] {c.doc_label}, p.{c.page}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
