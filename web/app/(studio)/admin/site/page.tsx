"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Stat } from "@/components/admin/ui";
import { useMe } from "@/components/shell/member-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";

interface Site {
  signups_open: boolean;
  jobs_paused: boolean;
  maintenance_message: string;
  referral_reward: number;
  referral_monthly_cap: number;
  referrals: { total: number; rewarded: number };
  trials_running: number;
}

export default function AdminSite() {
  const me = useMe();
  const owner = me.role === "owner";
  const [s, setS] = useState<Site | null>(null);
  const [d, setD] = useState<Partial<Site>>({});
  useEffect(() => {
    api<Site>("/admin/site").then(setS).catch(() => {});
  }, []);
  if (!s) return null;
  const v = { ...s, ...d };
  const save = async () => {
    try {
      const { signups_open, jobs_paused, maintenance_message, referral_reward, referral_monthly_cap } = v;
      setS(await api<Site>("/admin/site", { method: "PUT", json: { signups_open, jobs_paused, maintenance_message, referral_reward, referral_monthly_cap } }));
      setD({});
      toast.success("Saved. Changes are live for everyone.");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  return (
    <div className="grid max-w-3xl gap-6">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Referred sign-ups" value={s.referrals.total} />
        <Stat label="Rewarded referrals" value={s.referrals.rewarded} />
        <Stat label="Trials running" value={s.trials_running} />
      </div>
      <fieldset disabled={!owner} className="grid gap-6 disabled:opacity-70">
        <Card>
          <CardHeader>
            <CardTitle>Access</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <label className="flex items-center justify-between gap-3 text-sm">
              <span>
                Open sign-ups
                <span className="block text-xs text-muted-foreground">When off, only people you invite can create accounts.</span>
              </span>
              <Switch checked={v.signups_open} onCheckedChange={(x) => setD({ ...d, signups_open: x })} aria-label="Open sign-ups" />
            </label>
            <label className="flex items-center justify-between gap-3 text-sm">
              <span>
                Pause new jobs
                <span className="block text-xs text-muted-foreground">For maintenance. Running jobs finish; admins can still start jobs.</span>
              </span>
              <Switch checked={v.jobs_paused} onCheckedChange={(x) => setD({ ...d, jobs_paused: x })} aria-label="Pause new jobs" />
            </label>
            <Field label="Banner message (shown on every page while set)">
              <Textarea rows={2} maxLength={300} value={v.maintenance_message} onChange={(e) => setD({ ...d, maintenance_message: e.target.value })} aria-label="Banner message" />
            </Field>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Referral program</CardTitle>
            <CardDescription>Both people get the reward when the invited friend finishes their first video.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field label="Reward (tokens each)">
              <Input type="number" min={0} value={v.referral_reward} onChange={(e) => setD({ ...d, referral_reward: Number(e.target.value) })} aria-label="Referral reward" />
            </Field>
            <Field label="Max rewarded referrals per person per month">
              <Input type="number" min={0} value={v.referral_monthly_cap} onChange={(e) => setD({ ...d, referral_monthly_cap: Number(e.target.value) })} />
            </Field>
          </CardContent>
        </Card>
      </fieldset>
      {owner ? (
        <Button onClick={save} disabled={!Object.keys(d).length} className="justify-self-end" data-testid="save-site">
          Save
        </Button>
      ) : (
        <p className="text-sm text-muted-foreground">Only the owner can change these.</p>
      )}
    </div>
  );
}
