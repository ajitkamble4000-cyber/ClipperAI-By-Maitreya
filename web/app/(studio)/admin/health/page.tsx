"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, RefreshCcw, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

interface Health {
  ok: boolean;
  checks: Record<string, { ok: boolean; [k: string]: unknown }>;
}

const LABEL: Record<string, string> = { database: "Database", redis: "Queue (Redis)", storage: "File storage", workers: "Workers", ai: "AI providers" };

function describe(name: string, c: Health["checks"][string]): string {
  if (c.error) return String(c.error);
  if (name === "redis") {
    const q = c.queues as Record<string, number>;
    return `${c.ms} ms · waiting: ${Object.entries(q).map(([k, v]) => `${k} ${v}`).join(", ")}`;
  }
  if (name === "workers") return `${c.running} running · ${c.stale} stuck · ${c.waiting_long} waiting > 10 min`;
  if (name === "ai") return (c.configured as string[]).length ? `Configured: ${(c.configured as string[]).join(", ")}` : "No AI provider configured: add a key in Settings → AI providers";
  return `${c.ms} ms`;
}

export default function AdminHealth() {
  const [h, setH] = useState<Health | null>(null);
  const load = useCallback(() => api<Health>("/admin/health").then(setH).catch(() => {}), []);
  useEffect(() => {
    load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, [load]);
  if (!h) return null;
  return (
    <div className="grid max-w-3xl gap-3" data-testid="health">
      <div className="flex items-center gap-2">
        <p className="text-sm">{h.ok ? "Everything is working." : "Something needs attention."}</p>
        <Button variant="ghost" size="sm" onClick={load} className="ml-auto">
          <RefreshCcw /> Refresh
        </Button>
      </div>
      {Object.entries(h.checks).map(([name, c]) => (
        <div key={name} className="flex items-start gap-3 rounded-xl border p-4">
          {c.ok ? <CheckCircle2 className="mt-0.5 size-5 text-success" /> : <XCircle className="mt-0.5 size-5 text-destructive" />}
          <div>
            <p className="font-medium">{LABEL[name] ?? name}</p>
            <p className="text-sm text-muted-foreground">{describe(name, c)}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
