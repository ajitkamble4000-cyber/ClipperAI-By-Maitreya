"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, Coins, Minus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { api } from "@/lib/api";
import { env } from "@/lib/env";
import { FEATURES } from "@/lib/features";
import { supabaseBrowser } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

interface PublicPlan {
  id: string;
  name: string;
  description: string;
  daily_tokens: number | null;
  price_usd_month: number;
  features: string[];
  limits: Record<string, number | boolean>;
  highlight: boolean;
}
interface Price {
  action: string;
  label: string;
  tokens: number;
  unit: string;
  description: string;
}
interface MeLite {
  plan_id: string;
  unlimited: boolean;
}
interface Pending {
  plan_id: string;
  status: string;
}

const BASE = ["Paste any link or upload", "AI clips with titles & hashtags", "Animated captions, 6 styles", "AI story videos", "SRT / VTT / TXT caption files"];
const COMPARE: { label: string; get: (p: PublicPlan) => string | boolean }[] = [
  { label: "Tokens every day", get: (p) => (p.daily_tokens == null ? "Unlimited" : p.daily_tokens.toLocaleString()) },
  { label: "Clips per video", get: (p) => `up to ${p.limits.max_clips_per_job ?? 5}` },
  { label: "Longest source video", get: (p) => `${p.limits.max_source_minutes ?? 60} min` },
  { label: "Biggest upload", get: (p) => `${Math.round(Number(p.limits.max_upload_mb ?? 1024) / 1024)} GB` },
  { label: "Jobs at the same time", get: (p) => String(p.limits.concurrent_jobs ?? 1) },
  { label: "Links per batch", get: (p) => String(p.limits.max_batch ?? 1) },
  ...Object.entries(FEATURES)
    .filter(([k]) => k !== "templates" && k !== "priority")
    .map(([k, f]) => ({ label: f.label, get: (p: PublicPlan) => p.features.includes(k) })),
  { label: "Priority processing", get: (p) => p.features.includes("priority") },
];

export default function PricingPage() {
  const [plans, setPlans] = useState<PublicPlan[] | null>(null);
  const [prices, setPrices] = useState<Price[]>([]);
  const [me, setMe] = useState<MeLite | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [asking, setAsking] = useState<string | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    fetch(`${env.apiUrl}/plans`).then((r) => r.json()).then(setPlans).catch(() => setPlans([]));
    fetch(`${env.apiUrl}/public/token-prices`).then((r) => r.json()).then(setPrices).catch(() => {});
    supabaseBrowser()
      .auth.getSession()
      .then(({ data }) => {
        if (!data.session) return;
        api<MeLite>("/me").then(setMe).catch(() => {});
        api<Pending[]>("/billing/upgrade-request")
          .then((r) => setPending(r.find((x) => x.status === "pending") ?? null))
          .catch(() => {});
      });
  }, []);

  const request = async (planId: string) => {
    try {
      const r = await api<Pending>("/billing/upgrade-request", { method: "POST", json: { plan_id: planId, note } });
      setPending(r);
      setAsking(null);
      setNote("");
      toast.success("Request sent. You'll get a notification as soon as it's approved.");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const cta = (p: PublicPlan) => {
    if (!me) {
      return (
        <Button asChild className="w-full" variant={p.highlight ? "default" : "outline"}>
          <Link href="/signup">{p.price_usd_month ? `Start free, then ${p.name}` : "Start free"}</Link>
        </Button>
      );
    }
    if (me.unlimited) return <p className="text-center text-sm text-muted-foreground">Your team account has everything.</p>;
    if (me.plan_id === p.id) return <p className="rounded-lg border py-2 text-center text-sm font-medium" data-testid="current-plan">Your plan</p>;
    if (pending?.plan_id === p.id) return <p className="rounded-lg border border-primary/40 py-2 text-center text-sm text-primary">Request sent</p>;
    if (!p.price_usd_month) return null;
    return (
      <Button className="w-full" variant={p.highlight ? "default" : "outline"} onClick={() => setAsking(p.id)} disabled={!!pending} data-testid={`upgrade-${p.id}`}>
        Upgrade to {p.name}
      </Button>
    );
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-14">
      <div className="text-center">
        <h1 className="text-4xl font-bold tracking-tight">Simple pricing</h1>
        <p className="mt-3 text-muted-foreground">Every plan gets fresh tokens every day. Failed jobs are always refunded.</p>
      </div>

      <div className="mt-10 grid gap-4 md:grid-cols-3">
        {(plans ?? []).map((p) => (
          <div
            key={p.id}
            className={cn("flex flex-col rounded-2xl border p-6", p.highlight && "border-primary ring-1 ring-primary")}
            data-testid={`plan-${p.id}`}
          >
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">{p.name}</h2>
              {p.highlight && <span className="rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">Most popular</span>}
            </div>
            <p className="mt-1 min-h-10 text-sm text-muted-foreground">{p.description}</p>
            <p className="mt-4">
              <span className="text-4xl font-bold">${p.price_usd_month}</span>
              <span className="text-sm text-muted-foreground"> / month</span>
            </p>
            <p className="mt-1 flex items-center gap-1.5 text-sm">
              <Coins className="size-4 text-primary" />
              {p.daily_tokens == null ? "Unlimited" : p.daily_tokens.toLocaleString()} tokens every day
            </p>
            <ul className="mt-5 grid flex-1 content-start gap-2 text-sm">
              {[...BASE, ...p.features.filter((f) => FEATURES[f]).map((f) => FEATURES[f].label)].map((f) => (
                <li key={f} className="flex gap-2">
                  <Check className="mt-0.5 size-4 shrink-0 text-success" /> {f}
                </li>
              ))}
              {p.limits.watermark ? <li className="flex gap-2 text-muted-foreground"><Minus className="mt-0.5 size-4 shrink-0" /> Small watermark</li> : null}
            </ul>
            <div className="mt-6">{cta(p)}</div>
            {asking === p.id && (
              <div className="mt-3 grid gap-2">
                <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Anything we should know? (optional)" aria-label="Note" maxLength={500} />
                <div className="flex gap-2">
                  <Button className="flex-1" onClick={() => request(p.id)} data-testid="send-request">
                    Send request
                  </Button>
                  <Button variant="ghost" onClick={() => setAsking(null)}>
                    Cancel
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">The owner activates upgrades personally. You'll be notified in the app.</p>
              </div>
            )}
          </div>
        ))}
      </div>

      {plans && plans.length > 0 && (
        <div className="mt-14 overflow-x-auto">
          <h2 className="mb-4 text-xl font-semibold">Compare plans</h2>
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-2 font-medium text-muted-foreground">Feature</th>
                {plans.map((p) => (
                  <th key={p.id} className="py-2 font-semibold">
                    {p.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {COMPARE.map((row) => (
                <tr key={row.label} className="border-b border-border/50">
                  <td className="py-2 text-muted-foreground">{row.label}</td>
                  {plans.map((p) => {
                    const v = row.get(p);
                    return (
                      <td key={p.id} className="py-2">
                        {v === true ? <Check className="size-4 text-success" /> : v === false ? <Minus className="size-4 text-muted-foreground/50" /> : v}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {prices.length > 0 && (
        <div className="mt-14">
          <h2 className="text-xl font-semibold">What things cost</h2>
          <p className="mt-1 text-sm text-muted-foreground">Tokens are only spent when a job starts, and come back automatically if it fails.</p>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {prices.map((x) => (
              <div key={x.action} className="flex items-start justify-between gap-3 rounded-lg border p-3 text-sm">
                <span>
                  <span className="font-medium">{x.label}</span>
                  <span className="block text-xs text-muted-foreground">{x.description}</span>
                </span>
                <span className="shrink-0 tabular-nums">
                  {x.tokens} <span className="text-xs text-muted-foreground">/ {x.unit}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
