"use client";

import { useCallback, useEffect, useState } from "react";
import { BookmarkPlus, LayoutTemplate, X } from "lucide-react";
import { toast } from "sonner";
import { LockedBadge, useGate } from "@/components/plan/locked";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface Template {
  id: string;
  kind: "clip" | "story";
  name: string;
  settings: Record<string, unknown>;
  builtin: boolean;
}

/** Built-in starting points for everyone; saving your own is a Pro feature. */
export function TemplateBar({
  kind,
  onApply,
  current,
}: {
  kind: "clip" | "story";
  onApply: (settings: Record<string, unknown>, name: string) => void;
  current: () => Record<string, unknown>;
}) {
  const gate = useGate();
  const [items, setItems] = useState<Template[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");

  const load = useCallback(() => api<Template[]>(`/templates?kind=${kind}`).then(setItems).catch(() => {}), [kind]);
  useEffect(() => {
    load();
  }, [load]);

  const apply = (t: Template) => {
    setActive(t.id);
    onApply(t.settings, t.name);
    toast.success(`Template “${t.name}” applied`);
  };
  const save = async () => {
    try {
      await api("/templates", { method: "POST", json: { kind, name: name.trim(), settings: current() } });
      toast.success("Template saved");
      setNaming(false);
      setName("");
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const remove = async (t: Template) => {
    await api(`/templates/${t.id}`, { method: "DELETE" }).catch((e) => toast.error((e as Error).message));
    load();
  };

  return (
    <div className="grid gap-2" data-testid={`templates-${kind}`}>
      <p className="flex items-center gap-2 text-sm font-medium">
        <LayoutTemplate className="size-4 text-primary" /> Start from a template
      </p>
      <div className="flex flex-wrap gap-2">
        {items.map((t) => (
          <span key={t.id} className="group inline-flex items-center">
            <button
              type="button"
              onClick={() => apply(t)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs transition",
                active === t.id ? "border-primary bg-primary/10 text-primary" : "hover:border-primary/50",
                !t.builtin && "pr-1.5",
              )}
              data-testid="template-chip"
            >
              {t.name}
            </button>
            {!t.builtin && (
              <button type="button" onClick={() => remove(t)} aria-label={`Delete template ${t.name}`} className="-ml-1 rounded-full p-1 text-muted-foreground hover:text-destructive">
                <X className="size-3" />
              </button>
            )}
          </span>
        ))}
        {naming ? (
          <span className="inline-flex items-center gap-1">
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder="Template name" className="h-7 w-40 text-xs" aria-label="Template name" autoFocus />
            <Button size="sm" className="h-7" disabled={!name.trim()} onClick={save} data-testid="save-template">
              Save
            </Button>
            <Button size="sm" variant="ghost" className="h-7" onClick={() => setNaming(false)}>
              Cancel
            </Button>
          </span>
        ) : (
          <button
            type="button"
            onClick={() => (gate.allowed("templates") ? setNaming(true) : gate.explain("templates"))}
            className="inline-flex items-center gap-1 rounded-full border border-dashed px-3 py-1 text-xs text-muted-foreground hover:text-foreground"
            data-testid="new-template"
          >
            <BookmarkPlus className="size-3.5" /> Save current settings <LockedBadge feature="templates" className="ml-1" />
          </button>
        )}
      </div>
    </div>
  );
}
