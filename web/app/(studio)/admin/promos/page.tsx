"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Table } from "@/components/admin/ui";
import { useMe } from "@/components/shell/member-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";

interface Promo {
  code: string;
  kind: "tokens" | "trial";
  tokens: number;
  plan_id: string | null;
  trial_days: number | null;
  max_redemptions: number | null;
  redemptions: number;
  expires_at: string | null;
  active: boolean;
  note: string;
}

export default function AdminPromos() {
  const me = useMe();
  const owner = me.role === "owner";
  const [rows, setRows] = useState<Promo[]>([]);
  const [f, setF] = useState({ code: "", kind: "tokens", tokens: "500", plan_id: "pro", trial_days: "7", max: "", until: "", note: "" });
  const load = useCallback(() => api<Promo[]>("/admin/promos").then(setRows).catch(() => {}), []);
  useEffect(() => {
    load();
  }, [load]);

  const create = async () => {
    try {
      await api("/admin/promos", {
        method: "POST",
        json: {
          code: f.code,
          kind: f.kind,
          tokens: f.kind === "tokens" ? Number(f.tokens) : 0,
          plan_id: f.kind === "trial" ? f.plan_id : null,
          trial_days: f.kind === "trial" ? Number(f.trial_days) : null,
          max_redemptions: f.max ? Number(f.max) : null,
          expires_at: f.until ? new Date(f.until).toISOString() : null,
          note: f.note,
        },
      });
      toast.success(`Code ${f.code.toUpperCase()} created`);
      setF({ ...f, code: "", note: "" });
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const toggle = async (p: Promo) => {
    await api(`/admin/promos/${p.code}`, { method: "PATCH", json: { active: !p.active } }).catch((e) => toast.error((e as Error).message));
    load();
  };

  return (
    <div className="grid gap-6">
      {owner ? (
        <Card className="max-w-3xl">
          <CardHeader>
            <CardTitle>New promo code</CardTitle>
            <CardDescription>Give bonus tokens, or unlock a plan for a number of days (it switches back automatically).</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            <Field label="Code">
              <Input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} placeholder="LAUNCH50" aria-label="New code" className="font-mono" />
            </Field>
            <Field label="Gives">
              <Select value={f.kind} onValueChange={(v) => setF({ ...f, kind: v })} aria-label="Code type" options={[{ value: "tokens", label: "Bonus tokens" }, { value: "trial", label: "Plan trial" }]} />
            </Field>
            {f.kind === "tokens" ? (
              <Field label="Tokens">
                <Input type="number" min={1} value={f.tokens} onChange={(e) => setF({ ...f, tokens: e.target.value })} aria-label="Code tokens" />
              </Field>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <Field label="Plan">
                  <Select value={f.plan_id} onValueChange={(v) => setF({ ...f, plan_id: v })} options={[{ value: "pro", label: "Pro" }, { value: "business", label: "Business" }]} />
                </Field>
                <Field label="Days">
                  <Input type="number" min={1} max={365} value={f.trial_days} onChange={(e) => setF({ ...f, trial_days: e.target.value })} aria-label="Trial days" />
                </Field>
              </div>
            )}
            <Field label="Max uses (optional)">
              <Input type="number" min={1} value={f.max} onChange={(e) => setF({ ...f, max: e.target.value })} placeholder="Unlimited" />
            </Field>
            <Field label="Expires (optional)">
              <Input type="datetime-local" value={f.until} onChange={(e) => setF({ ...f, until: e.target.value })} />
            </Field>
            <Field label="Note (just for you)">
              <Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} maxLength={200} placeholder="Instagram giveaway" />
            </Field>
            <Button onClick={create} disabled={f.code.trim().length < 3} className="sm:col-start-3" data-testid="create-promo">
              Create code
            </Button>
          </CardContent>
        </Card>
      ) : (
        <p className="rounded-lg border p-3 text-sm text-muted-foreground">Only the owner can create promo codes.</p>
      )}
      <Table head={["Code", "Gives", "Used", "Expires", "Note", ""]} testId="promos-table">
        {rows.map((p) => (
          <tr key={p.code}>
            <td className="px-3 py-2 font-mono font-medium">{p.code}</td>
            <td className="px-3 py-2">{p.kind === "tokens" ? `${p.tokens.toLocaleString()} tokens` : `${p.plan_id} for ${p.trial_days} days`}</td>
            <td className="px-3 py-2 tabular-nums">
              {p.redemptions}
              {p.max_redemptions ? ` / ${p.max_redemptions}` : ""}
            </td>
            <td className="px-3 py-2 text-muted-foreground">{p.expires_at ? new Date(p.expires_at).toLocaleDateString() : "never"}</td>
            <td className="px-3 py-2 text-muted-foreground">{p.note}</td>
            <td className="px-3 py-2">
              {owner ? (
                <Button size="sm" variant="outline" onClick={() => toggle(p)}>
                  {p.active ? "Turn off" : "Turn on"}
                </Button>
              ) : (
                <span className="text-xs text-muted-foreground">{p.active ? "on" : "off"}</span>
              )}
            </td>
          </tr>
        ))}
      </Table>
    </div>
  );
}
