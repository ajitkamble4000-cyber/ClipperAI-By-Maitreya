"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, KeyRound, RefreshCcw } from "lucide-react";
import { toast } from "sonner";
import { Stat, Table } from "@/components/admin/ui";
import { useMe } from "@/components/shell/member-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { inr } from "@/lib/razorpay";
import { timeAgo } from "@/lib/utils";

interface Row {
  id: string;
  kind: string;
  description: string;
  amount: number;
  status: string;
  order_id: string;
  payment_id: string | null;
  error: string | null;
  created_at: string;
  paid_at: string | null;
  email: string;
  user_name: string;
}
interface Summary {
  revenue_30d: number;
  revenue_total: number;
  paid_30d: number;
  active_paid: number;
}
interface KeyStatus {
  source: "env" | "settings" | "none";
  key_id: string | null;
  mode: "test" | "live" | null;
  has_secret: boolean;
  has_webhook_secret: boolean;
  enabled: boolean;
  webhook_url: string;
}
interface Plan {
  id: string;
  name: string;
  price_inr_month: number;
  price_inr_year: number;
}
interface Pack {
  id: string;
  name: string;
  tokens: number;
  price_inr: number;
  active: boolean;
}

const STATUS_VARIANT: Record<string, "success" | "destructive" | "secondary" | "warning"> = {
  paid: "success",
  failed: "destructive",
  created: "secondary",
  refunded: "warning",
};

function RazorpayKeys({ owner }: { owner: boolean }) {
  const [s, setS] = useState<KeyStatus | null>(null);
  const [keyId, setKeyId] = useState("");
  const [secret, setSecret] = useState("");
  const [webhook, setWebhook] = useState("");
  const [copied, setCopied] = useState(false);
  const load = () =>
    api<KeyStatus>("/admin/payments/settings")
      .then((x) => {
        setS(x);
        setKeyId(x.key_id ?? "");
      })
      .catch(() => {});
  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    try {
      const body: Record<string, string> = {};
      if (keyId !== (s?.key_id ?? "")) body.key_id = keyId.trim();
      if (secret) body.key_secret = secret;
      if (webhook) body.webhook_secret = webhook;
      if (!Object.keys(body).length) return toast.message("Nothing to change");
      const r = await api<KeyStatus>("/admin/payments/settings", { method: "PUT", json: body });
      setS(r);
      setSecret("");
      setWebhook("");
      toast.success(r.enabled ? "Razorpay is connected. Payments are on." : "Saved");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const test = async () => {
    try {
      const r = await api<{ ok: boolean; mode: string }>("/admin/payments/test", { method: "POST" });
      toast.success(`Keys work (${r.mode} mode)`);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  if (!s) return null;
  return (
    <Card data-testid="razorpay-keys">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-4" /> Razorpay
          {s.enabled ? (
            <Badge variant={s.mode === "live" ? "success" : "warning"} data-testid="razorpay-status">
              {s.mode === "live" ? "Live" : "Test mode"}
            </Badge>
          ) : (
            <Badge variant="secondary" data-testid="razorpay-status">
              Not connected
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          From the Razorpay Dashboard → Account &amp; Settings → API keys. Start with Test keys (rzp_test_…), switch to Live keys after your account is
          activated. Secrets are stored encrypted and never shown again.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {s.source === "env" && <p className="text-sm text-muted-foreground">These keys come from the server's environment variables.</p>}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Key ID" htmlFor="rzp-key-id">
            <Input id="rzp-key-id" value={keyId} onChange={(e) => setKeyId(e.target.value)} placeholder="rzp_test_…" disabled={!owner || s.source === "env"} />
          </Field>
          <Field label="Key secret" htmlFor="rzp-key-secret" hint={s.has_secret ? "Saved. Type a new one to replace it." : undefined}>
            <Input id="rzp-key-secret" type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder={s.has_secret ? "••••••••" : ""} disabled={!owner || s.source === "env"} autoComplete="off" />
          </Field>
        </div>
        <div className="grid gap-2 rounded-lg border p-3">
          <p className="text-sm font-medium">Webhook (so payments are applied even if someone closes the tab)</p>
          <p className="text-xs text-muted-foreground">
            Razorpay Dashboard → Webhooks → Add: paste this URL, choose the events <b>payment.captured</b>, <b>order.paid</b> and <b>payment.failed</b>, set a
            secret, and paste the same secret here.
          </p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded bg-muted px-2 py-1.5 text-xs" data-testid="webhook-url">
              {s.webhook_url}
            </code>
            <Button
              size="icon"
              variant="ghost"
              aria-label="Copy webhook URL"
              onClick={() =>
                navigator.clipboard.writeText(s.webhook_url).then(() => {
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1200);
                })
              }
            >
              {copied ? <Check className="text-success" /> : <Copy />}
            </Button>
          </div>
          <Field label="Webhook secret" htmlFor="rzp-webhook-secret" hint={s.has_webhook_secret ? "Saved." : "Not set yet"}>
            <Input id="rzp-webhook-secret" type="password" value={webhook} onChange={(e) => setWebhook(e.target.value)} placeholder={s.has_webhook_secret ? "••••••••" : ""} disabled={!owner || s.source === "env"} autoComplete="off" />
          </Field>
        </div>
        {owner ? (
          <div className="flex gap-2">
            <Button onClick={save} disabled={s.source === "env"} data-testid="save-razorpay">
              Save
            </Button>
            <Button variant="outline" onClick={test} disabled={!s.enabled}>
              Test keys
            </Button>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">Only the owner can change payment keys.</p>
        )}
      </CardContent>
    </Card>
  );
}

function Prices({ owner }: { owner: boolean }) {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [packs, setPacks] = useState<Pack[]>([]);
  const load = () => {
    api<Plan[]>("/admin/plans").then((p) => setPlans(p.filter((x) => x.id !== "free" && x.id !== "team"))).catch(() => {});
    api<Pack[]>("/admin/token-packs").then(setPacks).catch(() => {});
  };
  useEffect(load, []);

  const savePlan = async (p: Plan) => {
    try {
      await api(`/admin/plans/${p.id}`, { method: "PUT", json: { price_inr_month: p.price_inr_month, price_inr_year: p.price_inr_year } });
      toast.success(`${p.name} prices saved`);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const savePack = async (p: Pack) => {
    try {
      await api(`/admin/token-packs/${p.id}`, { method: "PUT", json: { name: p.name, tokens: p.tokens, price_inr: p.price_inr, active: p.active } });
      toast.success(`${p.name} saved`);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const num = (v: string) => Math.max(0, Math.round(Number(v) || 0));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Prices (₹)</CardTitle>
        <CardDescription>Set a price to 0 to stop selling it online. Changes apply to new purchases right away.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        <div className="grid gap-2">
          {plans.map((p, i) => (
            <div key={p.id} className="grid items-end gap-2 sm:grid-cols-[1fr_140px_140px_auto]" data-testid={`price-row-${p.id}`}>
              <p className="pb-2 text-sm font-medium">{p.name}</p>
              <Field label="Per month">
                <Input inputMode="numeric" value={p.price_inr_month} disabled={!owner} onChange={(e) => setPlans((xs) => xs.map((x, j) => (j === i ? { ...x, price_inr_month: num(e.target.value) } : x)))} />
              </Field>
              <Field label="Per year">
                <Input inputMode="numeric" value={p.price_inr_year} disabled={!owner} onChange={(e) => setPlans((xs) => xs.map((x, j) => (j === i ? { ...x, price_inr_year: num(e.target.value) } : x)))} />
              </Field>
              {owner && (
                <Button variant="outline" onClick={() => savePlan(p)}>
                  Save
                </Button>
              )}
            </div>
          ))}
        </div>
        <div className="grid gap-2">
          <p className="text-sm font-medium">Token packs</p>
          {packs.map((p, i) => (
            <div key={p.id} className="grid items-end gap-2 sm:grid-cols-[1fr_130px_120px_auto_auto]">
              <Field label="Name">
                <Input value={p.name} disabled={!owner} onChange={(e) => setPacks((xs) => xs.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
              </Field>
              <Field label="Tokens">
                <Input inputMode="numeric" value={p.tokens} disabled={!owner} onChange={(e) => setPacks((xs) => xs.map((x, j) => (j === i ? { ...x, tokens: num(e.target.value) } : x)))} />
              </Field>
              <Field label="Price ₹">
                <Input inputMode="numeric" value={p.price_inr} disabled={!owner} onChange={(e) => setPacks((xs) => xs.map((x, j) => (j === i ? { ...x, price_inr: num(e.target.value) } : x)))} />
              </Field>
              <label className="flex items-center gap-2 pb-2 text-sm">
                <Switch checked={p.active} disabled={!owner} onCheckedChange={(v) => setPacks((xs) => xs.map((x, j) => (j === i ? { ...x, active: v } : x)))} /> On sale
              </label>
              {owner && (
                <Button variant="outline" onClick={() => savePack(p)}>
                  Save
                </Button>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export default function AdminPayments() {
  const me = useMe();
  const owner = me.role === "owner";
  const [state, setState] = useState("all");
  const [q, setQ] = useState("");
  const [data, setData] = useState<{ payments: Row[]; summary: Summary } | null>(null);
  const load = useCallback(() => {
    const p = new URLSearchParams({ limit: "200" });
    if (state !== "all") p.set("status", state);
    if (q.trim()) p.set("q", q.trim());
    api<{ payments: Row[]; summary: Summary }>(`/admin/payments?${p}`).then(setData).catch(() => {});
  }, [state, q]);
  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);
  const s = data?.summary;

  return (
    <div className="grid gap-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Revenue, last 30 days" value={s ? inr(s.revenue_30d / 100) : "…"} testId="revenue-30d" />
        <Stat label="Payments, last 30 days" value={s?.paid_30d ?? "…"} />
        <Stat label="Active paid plans" value={s?.active_paid ?? "…"} />
        <Stat label="Revenue, all time" value={s ? inr(s.revenue_total / 100) : "…"} />
      </div>

      <RazorpayKeys owner={owner} />
      <Prices owner={owner} />

      <div className="flex flex-col gap-2 sm:flex-row">
        <Input placeholder="Search email, order or payment id" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search payments" />
        <Select
          value={state}
          onValueChange={setState}
          className="sm:w-44"
          aria-label="Payment status"
          options={[
            { value: "all", label: "All payments" },
            { value: "paid", label: "Paid" },
            { value: "created", label: "Started, not paid" },
            { value: "failed", label: "Failed" },
          ]}
        />
        <Button variant="outline" size="icon" onClick={load} aria-label="Refresh">
          <RefreshCcw />
        </Button>
      </div>
      <Table head={["User", "Purchase", "Amount", "Status", "Razorpay", "When"]} testId="payments-table">
        {data?.payments.map((p) => (
          <tr key={p.id} className="hover:bg-muted/30">
            <td className="px-3 py-2">
              <span className="block font-medium">{p.user_name}</span>
              <span className="block text-xs text-muted-foreground">{p.email}</span>
            </td>
            <td className="px-3 py-2">{p.description}</td>
            <td className="px-3 py-2 tabular-nums">{inr(p.amount / 100)}</td>
            <td className="px-3 py-2">
              <Badge variant={STATUS_VARIANT[p.status] ?? "secondary"} className="capitalize">
                {p.status === "created" ? "not paid" : p.status}
              </Badge>
              {p.error && <span className="block text-xs text-destructive">{p.error}</span>}
            </td>
            <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
              {p.payment_id ?? "–"}
              <span className="block">{p.order_id}</span>
            </td>
            <td className="px-3 py-2 text-muted-foreground">{timeAgo(p.paid_at ?? p.created_at)}</td>
          </tr>
        ))}
      </Table>
      {data && data.payments.length === 0 && <p className="text-center text-sm text-muted-foreground">No payments yet.</p>}
    </div>
  );
}
