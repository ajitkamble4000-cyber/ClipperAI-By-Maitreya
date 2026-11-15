"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, OctagonX } from "lucide-react";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Summary {
  budget: { budget: number | null; spent: number; ratio: number; level: "ok" | "warn" | "blocked" };
  per_day: { day: string; cost: number; calls: number }[];
  per_user: { user_id: string | null; name: string; cost: number; calls: number }[];
  per_model: { model: string; kind: string; cost: number; calls: number; images: number; seconds: number; input_tokens: number; output_tokens: number }[];
  per_month: { month: string; cost: number; calls: number }[];
  recent: { ts: string; model: string; kind: string; cost_usd: number; name: string | null; project: string | null }[];
}

const usd = (n: number, digits = 2) => `$${n.toFixed(digits)}`;

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card>
      <CardContent className="p-5">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <p className="mt-1 text-3xl font-semibold tabular-nums">{value}</p>
        {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function BudgetMeter({ b }: { b: Summary["budget"] }) {
  if (!b.budget) return <StatTile label="Monthly budget" value="No limit" sub="An admin can set one in Settings → AI & budget" />;
  const pct = Math.min(100, Math.round(b.ratio * 100));
  const Icon = b.level === "blocked" ? OctagonX : b.level === "warn" ? AlertTriangle : CheckCircle2;
  const label = b.level === "blocked" ? "Budget reached: premium paused" : b.level === "warn" ? "Over 80%" : "On track";
  const color = b.level === "blocked" ? "bg-destructive" : b.level === "warn" ? "bg-warning" : "bg-success";
  return (
    <Card>
      <CardContent className="p-5">
        <p className="text-xs font-medium text-muted-foreground">Monthly budget</p>
        <p className="mt-1 text-3xl font-semibold tabular-nums">
          {pct}% <span className="text-base font-normal text-muted-foreground">of {usd(b.budget)}</span>
        </p>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Budget used">
          <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
          <Icon className="size-3.5" /> {label}
        </p>
      </CardContent>
    </Card>
  );
}

/** Single-series bar chart of daily spend: one hue, rounded data-ends on the baseline, hover tooltip. */
function DailyBars({ data }: { data: Summary["per_day"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 720;
  const H = 200;
  const pad = { l: 44, r: 8, t: 12, b: 24 };
  const max = Math.max(0.01, ...data.map((d) => d.cost));
  const nice = (() => {
    const p = 10 ** Math.floor(Math.log10(max));
    return [1, 2, 2.5, 5, 10].map((m) => m * p).find((v) => v >= max) ?? max;
  })();
  const iw = W - pad.l - pad.r;
  const ih = H - pad.t - pad.b;
  const slot = iw / data.length;
  const bw = Math.max(2, slot - 2); // 2px surface gap between bars
  const y = (v: number) => pad.t + ih - (v / nice) * ih;
  const ticks = [0, nice / 2, nice];
  const h = hover !== null ? data[hover] : null;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Daily AI spend, last 30 days" onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeWidth={1} />
            <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" fontSize={11} fill="var(--muted-foreground)">
              {usd(t, t < 1 && t > 0 ? 2 : 0)}
            </text>
          </g>
        ))}
        {data.map((d, i) => {
          const x = pad.l + i * slot + 1;
          const top = y(d.cost);
          const hgt = pad.t + ih - top;
          const r = Math.min(4, bw / 2, hgt);
          return (
            <g key={d.day} onMouseEnter={() => setHover(i)}>
              <rect x={pad.l + i * slot} y={pad.t} width={slot} height={ih} fill="transparent" />
              {d.cost > 0 && (
                <path
                  d={`M${x},${pad.t + ih} V${top + r} Q${x},${top} ${x + r},${top} H${x + bw - r} Q${x + bw},${top} ${x + bw},${top + r} V${pad.t + ih} Z`}
                  fill="var(--primary)"
                  opacity={hover === null || hover === i ? 1 : 0.45}
                />
              )}
            </g>
          );
        })}
        {[0, Math.floor(data.length / 2), data.length - 1].map((i) =>
          data[i] ? (
            <text key={i} x={pad.l + i * slot + slot / 2} y={H - 6} textAnchor="middle" fontSize={11} fill="var(--muted-foreground)">
              {new Date(data[i].day).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            </text>
          ) : null,
        )}
      </svg>
      {h && hover !== null && (
        <div
          className="pointer-events-none absolute top-0 rounded-md border bg-popover px-2 py-1 text-xs shadow"
          style={{ left: `${((pad.l + hover * slot + slot / 2) / W) * 100}%`, transform: "translateX(-50%)" }}
        >
          <p className="font-medium">{new Date(h.day).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</p>
          <p className="tabular-nums">
            {usd(h.cost, 3)} · {h.calls} calls
          </p>
        </div>
      )}
    </div>
  );
}

const isNumeric = (c: string | number) => typeof c === "number" || /^\$?[\d.,]+( [a-z]+)*$/.test(String(c));

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  const numericCol = head.map((_, j) => rows.length > 0 && rows.every((r) => isNumeric(r[j])));
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            {head.map((h, i) => (
              <th key={h} className={cn("px-2 py-2 font-medium first:pl-0 last:pr-0", numericCol[i] && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={head.length} className="py-4 text-center text-muted-foreground">
                No usage yet this month.
              </td>
            </tr>
          ) : (
            rows.map((r, i) => (
              <tr key={i} className="border-t">
                {r.map((c, j) => (
                  <td key={j} className={cn("px-2 py-2 first:pl-0 last:pr-0", numericCol[j] && "text-right tabular-nums")}>
                    {c}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function UsageView() {
  const [s, setS] = useState<Summary | null>(null);
  const [view, setView] = useState<"chart" | "table">("chart");
  useEffect(() => {
    api<Summary>("/usage/summary?days=30").then(setS).catch(() => {});
  }, []);
  const last30 = useMemo(() => (s ? s.per_day.reduce((a, d) => a + d.cost, 0) : 0), [s]);
  if (!s) return <Skeleton className="h-96" />;
  const thisMonth = s.per_month.at(-1)?.cost ?? 0;
  return (
    <>
      <PageHeader title="Usage & cost" description="Estimated Gemini spend, from the per-model price table in Settings." />
      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile label="This month" value={usd(thisMonth)} sub={`${s.per_month.at(-1)?.calls ?? 0} AI calls`} />
        <StatTile label="Last 30 days" value={usd(last30)} />
        <BudgetMeter b={s.budget} />
      </div>
      <Card className="mt-6">
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Daily spend</CardTitle>
          <Tabs value={view} onValueChange={(v) => setView(v as "chart" | "table")}>
            <TabsList>
              <TabsTrigger value="chart">Chart</TabsTrigger>
              <TabsTrigger value="table">Table</TabsTrigger>
            </TabsList>
          </Tabs>
        </CardHeader>
        <CardContent>
          {view === "chart" ? (
            <DailyBars data={s.per_day} />
          ) : (
            <Table head={["Day", "Calls", "Cost"]} rows={[...s.per_day].reverse().map((d) => [d.day, d.calls, usd(d.cost, 3)])} />
          )}
        </CardContent>
      </Card>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>By teammate (this month)</CardTitle>
          </CardHeader>
          <CardContent>
            <Table head={["Member", "Calls", "Cost"]} rows={s.per_user.map((u) => [u.name, u.calls, usd(u.cost)])} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>By model (this month)</CardTitle>
          </CardHeader>
          <CardContent>
            <Table
              head={["Model", "Use", "Calls", "Cost"]}
              rows={s.per_model.map((m) => [
                m.model,
                m.kind === "image" ? `${m.images} images` : m.kind === "video" ? `${m.seconds} s video` : `${((m.input_tokens + m.output_tokens) / 1000).toFixed(1)}k tokens`,
                m.calls,
                usd(m.cost),
              ])}
            />
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>By month</CardTitle>
          </CardHeader>
          <CardContent>
            <Table head={["Month", "Calls", "Cost"]} rows={[...s.per_month].reverse().map((m) => [m.month, m.calls, usd(m.cost)])} />
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Recent AI calls</CardTitle>
          </CardHeader>
          <CardContent>
            <Table
              head={["When", "Who", "Project", "Model", "Cost"]}
              rows={s.recent.map((r) => [new Date(r.ts).toLocaleString(), r.name ?? "—", r.project ?? "—", `${r.model} (${r.kind})`, usd(r.cost_usd, 4)])}
            />
          </CardContent>
        </Card>
      </div>
    </>
  );
}
