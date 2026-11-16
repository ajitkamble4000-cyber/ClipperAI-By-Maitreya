"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Clapperboard, Coins, Flame, Scissors, Timer } from "lucide-react";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Day {
  day: string;
  tokens: number;
  clips: number;
  jobs: number;
}
export interface Stats {
  days: number;
  since: string;
  totals: {
    videos_in: number;
    minutes_in: number;
    clips: number;
    minutes_out: number;
    avg_score: number | null;
    stories: number;
    jobs_ok: number;
    jobs_failed: number;
    tokens: number;
  };
  by_feature: { feature: string; tokens: number }[];
  daily: Day[];
  best_clips: { id: string; title: string; project_id: string; virality_score: number; duration_s: number }[];
  streak: number;
}

type Metric = "tokens" | "clips" | "jobs";
const METRICS: { id: Metric; label: string; title: string }[] = [
  { id: "tokens", label: "Tokens", title: "Tokens spent per day" },
  { id: "clips", label: "Clips", title: "Clips made per day" },
  { id: "jobs", label: "Jobs", title: "Finished jobs per day" },
];
const RANGES = [7, 30, 90] as const;

const fmt = (n: number) => n.toLocaleString();
const plural = (n: number, word: string) => `${fmt(n)} ${word}${n === 1 ? "" : "s"}`;
const shortDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

/** Round the axis top up to a clean number (1, 2, 5 × 10ⁿ). */
function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

function Tile({ icon: Icon, label, value, hint, testId }: { icon: typeof Coins; label: string; value: string; hint?: string; testId: string }) {
  return (
    <div className="rounded-xl border bg-card p-4" data-testid={testId}>
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Icon className="size-3.5" aria-hidden /> {label}
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/** One-series column chart: thin columns from a shared baseline, hover tooltip, table view. */
function DailyChart({ days, metric }: { days: Day[]; metric: Metric }) {
  const [hover, setHover] = useState<number | null>(null);
  const values = days.map((d) => Math.max(0, d[metric]));
  const top = niceMax(Math.max(...values, 0));
  const peak = values.indexOf(Math.max(...values));
  const labelAt = new Set([0, Math.floor((days.length - 1) / 2), days.length - 1]);
  const h = hover !== null ? days[hover] : null;

  return (
    <div>
      <div className="relative flex h-48 gap-2" onMouseLeave={() => setHover(null)}>
        {/* y-axis ticks */}
        <div className="flex w-10 shrink-0 flex-col justify-between text-right text-[11px] tabular-nums text-muted-foreground">
          <span>{fmt(top)}</span>
          <span>{fmt(top / 2)}</span>
          <span>0</span>
        </div>
        <div className="relative flex-1" data-testid="daily-chart">
          {/* hairline grid */}
          {[0, 50, 100].map((p) => (
            <div key={p} className="absolute inset-x-0 border-t border-border/60" style={{ top: `${p}%` }} aria-hidden />
          ))}
          <div className="absolute inset-0 flex items-end gap-[2px]">
            {days.map((d, i) => {
              const v = values[i];
              return (
                <div
                  key={d.day}
                  className="flex h-full min-w-0 flex-1 cursor-default items-end justify-center"
                  onMouseEnter={() => setHover(i)}
                  onFocus={() => setHover(i)}
                  tabIndex={0}
                  role="img"
                  aria-label={`${shortDate(d.day)}: ${fmt(v)} ${metric}`}
                  data-testid="day-bar"
                >
                  <div
                    className={cn("w-full max-w-6 rounded-t bg-primary transition-opacity", hover !== null && hover !== i && "opacity-50")}
                    style={{ height: v ? `max(${(v / top) * 100}%, 3px)` : 0 }}
                  />
                </div>
              );
            })}
          </div>
          {/* peak label, only when nothing is hovered */}
          {hover === null && values[peak] > 0 && (
            <span
              className="pointer-events-none absolute -translate-x-1/2 -translate-y-full pb-1 text-[11px] font-medium tabular-nums"
              style={{ left: `${((peak + 0.5) / days.length) * 100}%`, bottom: `${(values[peak] / top) * 100}%` }}
            >
              {fmt(values[peak])}
            </span>
          )}
          {h && hover !== null && (
            <div
              className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 rounded-lg border bg-popover px-2.5 py-1.5 text-xs shadow-lg"
              style={{ left: `${Math.min(88, Math.max(12, ((hover + 0.5) / days.length) * 100))}%` }}
              data-testid="chart-tooltip"
            >
              <p className="font-medium">{shortDate(h.day)}</p>
              <p className="text-muted-foreground">
                {plural(h.tokens, "token")} · {plural(h.clips, "clip")} · {plural(h.jobs, "job")}
              </p>
            </div>
          )}
        </div>
      </div>
      <div className="relative ml-12 mt-1 h-4 whitespace-nowrap text-[11px] text-muted-foreground" aria-hidden>
        {[...labelAt].map((i) => (
          <span
            key={i}
            className="absolute"
            style={
              i === 0
                ? { left: 0 }
                : i === days.length - 1
                  ? { right: 0 }
                  : { left: `${((i + 0.5) / days.length) * 100}%`, transform: "translateX(-50%)" }
            }
          >
            {shortDate(days[i].day)}
          </span>
        ))}
      </div>
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-xs text-muted-foreground">View as table</summary>
        <div className="mt-2 max-h-60 overflow-auto rounded-lg border">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-muted text-left">
              <tr>
                <th className="px-3 py-1.5 font-medium">Day</th>
                <th className="px-3 py-1.5 text-right font-medium">Tokens</th>
                <th className="px-3 py-1.5 text-right font-medium">Clips</th>
                <th className="px-3 py-1.5 text-right font-medium">Jobs</th>
              </tr>
            </thead>
            <tbody>
              {[...days].reverse().map((d) => (
                <tr key={d.day} className="border-t">
                  <td className="px-3 py-1">{shortDate(d.day)}</td>
                  <td className="px-3 py-1 text-right tabular-nums">{fmt(d.tokens)}</td>
                  <td className="px-3 py-1 text-right tabular-nums">{fmt(d.clips)}</td>
                  <td className="px-3 py-1 text-right tabular-nums">{fmt(d.jobs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

function Segmented<T extends string | number>({ value, options, onChange, label }: { value: T; options: { id: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg border p-0.5">
      {options.map((o) => (
        <button
          key={String(o.id)}
          type="button"
          aria-pressed={o.id === value}
          onClick={() => onChange(o.id)}
          className={cn("rounded-md px-3 py-1 text-xs font-medium", o.id === value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function StatsView() {
  const [range, setRange] = useState<number>(30);
  const [metric, setMetric] = useState<Metric>("tokens");
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setStats(null);
    api<Stats>(`/me/stats?days=${range}`)
      .then(setStats)
      .catch((e) => setError((e as Error).message));
  }, [range]);

  const featureTop = useMemo(() => Math.max(1, ...(stats?.by_feature.map((f) => f.tokens) ?? [1])), [stats]);
  const t = stats?.totals;
  const finished = t ? t.jobs_ok + t.jobs_failed : 0;

  return (
    <>
      <PageHeader
        title="Your stats"
        description="What you've made and what it cost."
        actions={<Segmented label="Time range" value={range} onChange={setRange} options={RANGES.map((d) => ({ id: d, label: `${d} days` }))} />}
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      {!stats || !t ? (
        <div className="grid gap-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
          <Skeleton className="h-72" />
        </div>
      ) : (
        <div className="grid gap-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            <Tile icon={Scissors} label="Clips made" value={fmt(t.clips)} hint={`${t.minutes_out} min of Shorts`} testId="stat-clips" />
            <Tile icon={Timer} label="Video processed" value={`${t.minutes_in} min`} hint={plural(t.videos_in, "video")} testId="stat-minutes" />
            <Tile icon={Clapperboard} label="Stories rendered" value={fmt(t.stories)} testId="stat-stories" />
            <Tile icon={Coins} label="Tokens spent" value={fmt(t.tokens)} hint="after refunds" testId="stat-tokens" />
            <Tile
              icon={CheckCircle2}
              label="Jobs finished"
              value={fmt(t.jobs_ok)}
              hint={finished ? `${Math.round((t.jobs_ok / finished) * 100)}% succeeded` : "None yet"}
              testId="stat-jobs"
            />
            <Tile icon={Flame} label="Day streak" value={fmt(stats.streak)} hint={stats.streak ? (stats.streak === 1 ? "day in a row" : "days in a row") : "Make something today"} testId="stat-streak" />
          </div>

          <Card>
            <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
              <div>
                <CardTitle>{METRICS.find((m) => m.id === metric)?.title}</CardTitle>
                <CardDescription>
                  Last {stats.days} days, since {shortDate(stats.since)}
                </CardDescription>
              </div>
              <Segmented label="Chart metric" value={metric} onChange={setMetric} options={METRICS} />
            </CardHeader>
            <CardContent>
              <DailyChart days={stats.daily} metric={metric} />
            </CardContent>
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Tokens by feature</CardTitle>
                <CardDescription>Where your tokens went (refunds already taken off).</CardDescription>
              </CardHeader>
              <CardContent>
                {stats.by_feature.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No tokens spent in this period.</p>
                ) : (
                  <ul className="grid gap-2.5" data-testid="by-feature">
                    {stats.by_feature.map((f) => (
                      <li key={f.feature} className="grid grid-cols-[120px_1fr] items-center gap-3 text-sm">
                        <span className="truncate text-muted-foreground">{f.feature}</span>
                        <span className="flex items-center gap-2">
                          <span className="h-3 rounded-r bg-primary" style={{ width: `${(f.tokens / featureTop) * 85}%`, minWidth: 3 }} aria-hidden />
                          <span className="tabular-nums">{fmt(f.tokens)}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Best clips</CardTitle>
                <CardDescription>{t.avg_score !== null ? `Average virality score ${t.avg_score}` : "Your highest-scoring clips show up here."}</CardDescription>
              </CardHeader>
              <CardContent>
                {stats.best_clips.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No clips in this period. <Link href="/clipper/new" className="text-primary hover:underline">Make some</Link>
                  </p>
                ) : (
                  <ol className="grid gap-1.5" data-testid="best-clips">
                    {stats.best_clips.map((c, i) => (
                      <li key={c.id}>
                        <Link href={`/clipper/${c.project_id}`} className="flex items-center gap-3 rounded-lg border px-3 py-2 text-sm hover:border-primary/50">
                          <span className="w-4 text-xs text-muted-foreground">{i + 1}</span>
                          <span className="min-w-0 flex-1 truncate">{c.title || "Untitled clip"}</span>
                          <span className="text-xs text-muted-foreground">{Math.round(c.duration_s)} s</span>
                          <Badge variant="secondary" className="tabular-nums">
                            {c.virality_score}
                          </Badge>
                        </Link>
                      </li>
                    ))}
                  </ol>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
