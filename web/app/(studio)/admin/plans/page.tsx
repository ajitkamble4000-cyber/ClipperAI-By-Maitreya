"use client";

import { useCallback, useEffect, useState } from "react";
import { Gift } from "lucide-react";
import { toast } from "sonner";
import { useMe } from "@/components/shell/member-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { FEATURES } from "@/lib/features";

interface Plan {
  id: string;
  name: string;
  description: string;
  daily_tokens: number | null;
  price_usd_month: number;
  features: string[];
  limits: Record<string, number | boolean>;
  public: boolean;
  highlight: boolean;
  users: number;
}
interface Price {
  action: string;
  label: string;
  tokens: number;
  unit: string;
  description: string;
}

const BASE = ["clipper", "captions", "story", "exports", "basic_voices"];
const LIMITS: { key: string; label: string }[] = [
  { key: "max_clips_per_job", label: "Clips per video" },
  { key: "max_source_minutes", label: "Longest video (min)" },
  { key: "max_upload_mb", label: "Biggest upload (MB)" },
  { key: "concurrent_jobs", label: "Jobs at once" },
  { key: "max_batch", label: "Links per batch" },
];

function PlanCard({ plan, owner, onSaved }: { plan: Plan; owner: boolean; onSaved: () => void }) {
  const [d, setD] = useState<Plan>(plan);
  useEffect(() => setD(plan), [plan]);
  const dirty = JSON.stringify(d) !== JSON.stringify(plan);
  const save = async () => {
    try {
      await api(`/admin/plans/${plan.id}`, {
        method: "PUT",
        json: {
          name: d.name,
          description: d.description,
          price_usd_month: d.price_usd_month,
          ...(d.daily_tokens == null ? { unlimited: true } : { daily_tokens: d.daily_tokens }),
          features: [...BASE, ...d.features], // base features are always on; the editor only shows the extras
          limits: d.limits,
          public: d.public,
          highlight: d.highlight,
        },
      });
      toast.success(`${d.name} saved`);
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const toggle = (f: string) => setD((x) => ({ ...x, features: x.features.includes(f) ? x.features.filter((y) => y !== f) : [...x.features, f] }));

  return (
    <Card data-testid={`admin-plan-${plan.id}`}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>{plan.name}</span>
          <span className="text-sm font-normal text-muted-foreground">{plan.users} users</span>
        </CardTitle>
        <CardDescription>{plan.public ? "Shown on the pricing page" : "Hidden (internal)"}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <fieldset disabled={!owner} className="grid gap-4 disabled:opacity-70">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Price (USD / month)">
              <Input type="number" min={0} step={1} value={d.price_usd_month} onChange={(e) => setD({ ...d, price_usd_month: Number(e.target.value) })} aria-label={`${plan.name} price`} />
            </Field>
            <Field label="Tokens per day">
              <Input
                type="number"
                min={0}
                value={d.daily_tokens ?? ""}
                placeholder="Unlimited"
                onChange={(e) => setD({ ...d, daily_tokens: e.target.value === "" ? null : Number(e.target.value) })}
                aria-label={`${plan.name} daily tokens`}
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {LIMITS.map((l) => (
              <Field key={l.key} label={l.label}>
                <Input type="number" min={0} value={Number(d.limits[l.key] ?? 0)} onChange={(e) => setD({ ...d, limits: { ...d.limits, [l.key]: Number(e.target.value) } })} />
              </Field>
            ))}
            <label className="flex items-center justify-between gap-2 self-end text-sm">
              Watermark
              <Switch checked={Boolean(d.limits.watermark)} onCheckedChange={(v) => setD({ ...d, limits: { ...d.limits, watermark: v } })} />
            </label>
          </div>
          <div>
            <p className="mb-2 text-sm font-medium">Features</p>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {Object.entries(FEATURES).map(([k, f]) => (
                <label key={k} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={d.features.includes(k)} onChange={() => toggle(k)} className="size-4 accent-[var(--primary)]" />
                  {f.label}
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-6 text-sm">
            <label className="flex items-center gap-2">
              <Switch checked={d.public} onCheckedChange={(v) => setD({ ...d, public: v })} /> Public
            </label>
            <label className="flex items-center gap-2">
              <Switch checked={d.highlight} onCheckedChange={(v) => setD({ ...d, highlight: v })} /> Most popular
            </label>
          </div>
        </fieldset>
        {owner && (
          <Button onClick={save} disabled={!dirty} className="justify-self-end" data-testid={`save-plan-${plan.id}`}>
            Save {plan.name}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

export default function AdminPlans() {
  const me = useMe();
  const owner = me.role === "owner";
  const [plans, setPlans] = useState<Plan[]>([]);
  const [prices, setPrices] = useState<Price[]>([]);
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [gift, setGift] = useState({ amount: "", plan: "all", note: "" });

  const load = useCallback(() => {
    api<Plan[]>("/admin/plans").then((p) => setPlans(p.map((x) => ({ ...x, features: x.features.filter((f) => !BASE.includes(f)) }))));
    api<Price[]>("/tokens/prices").then(setPrices);
  }, []);
  useEffect(load, [load]);

  const savePrice = async (action: string) => {
    try {
      await api(`/admin/token-prices/${action}`, { method: "PUT", json: { tokens: Number(edit[action]) } });
      toast.success("Price updated");
      setEdit((x) => {
        const next = { ...x };
        delete next[action];
        return next;
      });
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const broadcast = async () => {
    try {
      const r = await api<{ users: number }>("/admin/tokens/broadcast", {
        method: "POST",
        json: { amount: Number(gift.amount), plan_id: gift.plan === "all" ? null : gift.plan, note: gift.note },
      });
      toast.success(`Sent ${Number(gift.amount).toLocaleString()} tokens to ${r.users} users`);
      setGift({ amount: "", plan: "all", note: "" });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="grid gap-8">
      {!owner && <p className="rounded-lg border p-3 text-sm text-muted-foreground">Only the owner can change plans and send promotions. Admins can adjust token prices.</p>}
      <section className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        {plans.map((p) => (
          <PlanCard key={p.id} plan={p} owner={owner} onSaved={load} />
        ))}
      </section>

      <section>
        <h2 className="mb-1 text-lg font-semibold">Token prices</h2>
        <p className="mb-4 text-sm text-muted-foreground">What each action costs. Changes apply to new jobs right away.</p>
        <div className="grid gap-2 md:grid-cols-2">
          {prices.map((p) => (
            <div key={p.action} className="flex items-center gap-3 rounded-lg border p-3 text-sm" data-testid={`price-${p.action}`}>
              <span className="min-w-0 flex-1">
                {p.label}
                <span className="block text-xs text-muted-foreground">
                  per {p.unit} · {p.description}
                </span>
              </span>
              <Input
                type="number"
                min={0}
                className="w-24"
                value={edit[p.action] ?? String(p.tokens)}
                onChange={(e) => setEdit((x) => ({ ...x, [p.action]: e.target.value }))}
                aria-label={`${p.label} tokens`}
              />
              <Button size="sm" variant="outline" disabled={edit[p.action] === undefined || Number(edit[p.action]) === p.tokens} onClick={() => savePrice(p.action)}>
                Save
              </Button>
            </div>
          ))}
        </div>
      </section>

      {owner && (
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Gift className="size-4" /> Gift tokens to everyone
            </CardTitle>
            <CardDescription>Bonus tokens for every active user (team members already have unlimited). They get a notification.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <Field label="Tokens" className="sm:w-28">
              <Input type="number" min={1} value={gift.amount} onChange={(e) => setGift({ ...gift, amount: e.target.value })} aria-label="Gift amount" />
            </Field>
            <Field label="Who" className="sm:w-36">
              <Select
                value={gift.plan}
                onValueChange={(v) => setGift({ ...gift, plan: v })}
                options={[{ value: "all", label: "All users" }, ...plans.filter((p) => p.public).map((p) => ({ value: p.id, label: `${p.name} users` }))]}
              />
            </Field>
            <Field label="Message" className="flex-1">
              <Input value={gift.note} onChange={(e) => setGift({ ...gift, note: e.target.value })} placeholder="Happy Diwali!" maxLength={300} />
            </Field>
            <Button disabled={!gift.amount || Number(gift.amount) <= 0} onClick={broadcast}>
              Send
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
