"use client";

import { cn } from "@/lib/utils";

export function Stat({ label, value, hint, className, testId }: { label: string; value: React.ReactNode; hint?: React.ReactNode; className?: string; testId?: string }) {
  return (
    <div className={cn("rounded-xl border bg-card p-4", className)} data-testid={testId}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/** Minimal bar chart (no chart library): one bar per point, value on hover. */
export function Bars({ data, label, color = "bg-primary" }: { data: { x: string; y: number; y2?: number }[]; label: string; color?: string }) {
  const max = Math.max(1, ...data.map((d) => d.y + (d.y2 ?? 0)));
  return (
    <figure className="rounded-xl border bg-card p-4">
      <figcaption className="mb-3 text-sm font-medium">{label}</figcaption>
      <div className="flex h-28 items-end gap-[3px]" role="img" aria-label={label}>
        {data.map((d) => (
          <div key={d.x} className="flex h-full flex-1 flex-col justify-end" title={`${d.x}: ${d.y}${d.y2 !== undefined ? ` ok, ${d.y2} failed` : ""}`}>
            {d.y2 ? <div className="w-full rounded-t-sm bg-destructive/70" style={{ height: `${(d.y2 / max) * 100}%` }} /> : null}
            <div className={cn("w-full", d.y2 ? "" : "rounded-t-sm", color)} style={{ height: `${(d.y / max) * 100}%`, minHeight: d.y ? 2 : 0 }} />
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
        <span>{data[0]?.x.slice(5)}</span>
        <span>{data[data.length - 1]?.x.slice(5)}</span>
      </div>
    </figure>
  );
}

export function Table({ head, children, testId }: { head: string[]; children: React.ReactNode; testId?: string }) {
  return (
    <div className="overflow-x-auto rounded-xl border">
      <table className="w-full min-w-[640px] text-sm" data-testid={testId}>
        <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
          <tr>
            {head.map((h) => (
              <th key={h} className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">{children}</tbody>
      </table>
    </div>
  );
}

export const STATUS_COLOR: Record<string, string> = {
  succeeded: "text-success",
  failed: "text-destructive",
  canceled: "text-muted-foreground",
  running: "text-primary",
  queued: "text-warning",
  pending: "text-warning",
  approved: "text-success",
  declined: "text-destructive",
  active: "text-success",
  suspended: "text-destructive",
};
