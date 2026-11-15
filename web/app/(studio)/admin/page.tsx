"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bars, Stat } from "@/components/admin/ui";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

interface Overview {
  users: { total: number; new_7d: number; active_1d: number; active_7d: number; suspended: number; team: number };
  by_plan: { id: string; name: string; price_usd_month: number; users: number }[];
  mrr_usd: number;
  jobs: { today: number; active: number; failed_1d: number; ok_1d: number; success_rate: number | null };
  tokens: { d1: number; d7: number; d30: number; refunded_30d: number; waived_30d: number };
  ai: { budget: number | null; spent: number; ratio: number; level: string };
  signups: { day: string; n: number }[];
  jobs_per_day: { day: string; ok: number; failed: number }[];
  top_users: { user_id: string; name: string; email: string; plan_id: string; team: string | null; tokens: number }[];
  job_kinds: { kind: string; n: number }[];
  pending_upgrades: number;
}

export default function AdminOverview() {
  const [o, setO] = useState<Overview | null>(null);
  useEffect(() => {
    api<Overview>("/admin/overview").then(setO).catch(() => {});
  }, []);
  if (!o) return <Skeleton className="h-96" />;
  const n = (x: number) => x.toLocaleString();
  return (
    <div className="grid gap-6" data-testid="admin-overview">
      {o.pending_upgrades > 0 && (
        <Link href="/admin/requests" className="rounded-xl border border-primary/40 bg-primary/5 p-3 text-sm hover:bg-primary/10">
          {o.pending_upgrades} upgrade request{o.pending_upgrades > 1 ? "s" : ""} waiting for you →
        </Link>
      )}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Users" value={n(o.users.total)} hint={`+${o.users.new_7d} this week · ${o.users.team} on teams`} testId="stat-users" />
        <Stat label="Active" value={n(o.users.active_1d)} hint={`today · ${n(o.users.active_7d)} this week`} />
        <Stat label="Monthly revenue (plans)" value={`$${n(o.mrr_usd)}`} hint="List price × users on paid plans" />
        <Stat
          label="AI cost this month"
          value={`$${o.ai.spent.toFixed(2)}`}
          hint={o.ai.budget ? `${Math.round(o.ai.ratio * 100)}% of $${o.ai.budget} budget` : "No budget set"}
        />
        <Stat label="Jobs today" value={n(o.jobs.today)} hint={`${o.jobs.active} running now`} />
        <Stat
          label="Success rate (24 h)"
          value={o.jobs.success_rate == null ? "–" : `${Math.round(o.jobs.success_rate * 100)}%`}
          hint={`${o.jobs.failed_1d} failed`}
        />
        <Stat label="Tokens spent" value={n(o.tokens.d1)} hint={`today · ${n(o.tokens.d7)} this week · ${n(o.tokens.d30)} in 30 days`} />
        <Stat label="Refunded (30 days)" value={n(o.tokens.refunded_30d)} hint={`${n(o.tokens.waived_30d)} free for team & admins`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Bars label="Sign-ups (30 days)" data={o.signups.map((d) => ({ x: String(d.day), y: Number(d.n) }))} />
        <Bars label="Jobs per day (14 days, red = failed)" data={o.jobs_per_day.map((d) => ({ x: String(d.day), y: Number(d.ok), y2: Number(d.failed) }))} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl border bg-card p-4">
          <p className="mb-3 text-sm font-medium">Users by plan</p>
          {o.by_plan.map((p) => (
            <div key={p.id} className="flex justify-between py-1 text-sm">
              <span>{p.name}</span>
              <span className="tabular-nums text-muted-foreground">{p.users}</span>
            </div>
          ))}
        </div>
        <div className="rounded-xl border bg-card p-4">
          <p className="mb-3 text-sm font-medium">Top spenders (30 days)</p>
          {o.top_users.length === 0 && <p className="text-sm text-muted-foreground">No spending yet.</p>}
          {o.top_users.map((u) => (
            <Link key={u.user_id} href={`/admin/users/${u.user_id}`} className="flex justify-between gap-2 py-1 text-sm hover:text-primary">
              <span className="truncate">{u.name}</span>
              <span className="tabular-nums text-muted-foreground">{n(Number(u.tokens))}</span>
            </Link>
          ))}
        </div>
        <div className="rounded-xl border bg-card p-4">
          <p className="mb-3 text-sm font-medium">What people make (30 days)</p>
          {o.job_kinds.map((k) => (
            <div key={k.kind} className="flex justify-between py-1 text-sm">
              <span>{k.kind.replace(/_/g, " ")}</span>
              <span className="tabular-nums text-muted-foreground">{k.n}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
