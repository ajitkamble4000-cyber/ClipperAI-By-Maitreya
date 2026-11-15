"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight, Coins, Link2, LogOut, Palette, Receipt, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { LockedBadge } from "@/components/plan/locked";
import { PageHeader } from "@/components/shell/page-header";
import { hasFeature, useMe } from "@/components/shell/member-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { supabaseBrowser } from "@/lib/supabase/client";
import { timeAgo } from "@/lib/utils";

interface Req {
  id: string;
  plan_id: string;
  plan_name: string;
  status: string;
  reply: string;
  created_at: string;
}
interface ShareLink {
  token: string;
  title: string;
  views: number;
  expires_at: string | null;
  revoked_at: string | null;
}

export default function AccountPage() {
  const me = useMe();
  const router = useRouter();
  const [name, setName] = useState(me.display_name ?? "");
  const [reqs, setReqs] = useState<Req[]>([]);
  const [links, setLinks] = useState<ShareLink[]>([]);
  const [confirm, setConfirm] = useState("");

  const load = () => {
    api<Req[]>("/billing/upgrade-request").then(setReqs).catch(() => {});
    api<ShareLink[]>("/share-links").then(setLinks).catch(() => {});
  };
  useEffect(load, []);
  const pending = reqs.find((r) => r.status === "pending");
  const lastDecision = reqs.find((r) => r.status === "approved" || r.status === "declined");

  const saveName = async () => {
    try {
      await api("/me", { method: "PATCH", json: { display_name: name.trim() } });
      toast.success("Saved");
      router.refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const signOut = async () => {
    await supabaseBrowser().auth.signOut();
    router.replace("/login");
    router.refresh();
  };
  const remove = async () => {
    try {
      await api("/me", { method: "DELETE" });
      await supabaseBrowser().auth.signOut();
      router.replace("/welcome");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const revoke = async (token: string) => {
    await api(`/share-links/${token}`, { method: "DELETE" }).catch((e) => toast.error((e as Error).message));
    load();
  };

  const planLabel = me.role === "owner" ? "Owner" : me.team ? `${me.team[0].toUpperCase()}${me.team.slice(1)} team` : me.plan.name;

  return (
    <div className="grid max-w-3xl gap-6">
      <PageHeader title="Account" description={me.email} />

      <Card>
        <CardHeader>
          <CardTitle>Plan</CardTitle>
          <CardDescription>
            {me.unlimited ? "Everything is unlocked and free for your account." : `${me.plan.name}: ${me.plan.daily_tokens?.toLocaleString()} tokens every day.`}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-primary/15 px-3 py-1 text-sm font-medium text-primary" data-testid="account-plan">
              {planLabel}
            </span>
            {!me.unlimited && (
              <Button asChild variant="outline" size="sm">
                <Link href="/pricing">{me.plan_id === "business" ? "Compare plans" : "Upgrade"}</Link>
              </Button>
            )}
          </div>
          {pending && (
            <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground" data-testid="pending-request">
              You asked for {pending.plan_name} {timeAgo(pending.created_at)}. We'll notify you when it's approved.
              <button
                type="button"
                className="text-primary hover:underline"
                onClick={() => api("/billing/upgrade-request", { method: "DELETE" }).then(load)}
              >
                Cancel request
              </button>
            </p>
          )}
          {!pending && lastDecision?.status === "declined" && lastDecision.reply && (
            <p className="text-sm text-muted-foreground">
              Your {lastDecision.plan_name} request was declined: {lastDecision.reply}
            </p>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2">
        {[
          { href: "/account/tokens", icon: Coins, label: "Tokens & history", hint: "Balance, refills and every charge" },
          { href: "/account/brand", icon: Palette, label: "Brand kit", hint: "Logo, @handle and colours", feature: "brand_kit" },
          { href: "/pricing", icon: Receipt, label: "Plans & pricing", hint: "What each plan includes" },
        ].map((x) => (
          <Link key={x.href} href={x.href} className="flex items-center gap-3 rounded-xl border p-4 hover:border-primary/50">
            <x.icon className="size-5 text-primary" />
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2 text-sm font-medium">
                {x.label} {x.feature && <LockedBadge feature={x.feature} />}
              </span>
              <span className="block text-xs text-muted-foreground">{x.hint}</span>
            </span>
            <ChevronRight className="size-4 text-muted-foreground" />
          </Link>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <Field label="Display name" className="flex-1">
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} aria-label="Display name" />
          </Field>
          <Button onClick={saveName} disabled={!name.trim() || name.trim() === (me.display_name ?? "")}>
            Save
          </Button>
        </CardContent>
      </Card>

      {hasFeature(me, "share_links") && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Link2 className="size-4" /> Share links
            </CardTitle>
            <CardDescription>Links anyone can open to watch a video. Turn one off any time.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2">
            {links.length === 0 && <p className="text-sm text-muted-foreground">No links yet. Use Share on a finished clip.</p>}
            {links.map((l) => {
              const off = !!l.revoked_at || (l.expires_at && new Date(l.expires_at) < new Date());
              return (
                <div key={l.token} className="flex items-center gap-3 text-sm">
                  <span className="min-w-0 flex-1 truncate">{l.title}</span>
                  <span className="text-xs text-muted-foreground">{l.views} views</span>
                  {off ? (
                    <span className="text-xs text-muted-foreground">off</span>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="text-xs text-primary hover:underline"
                        onClick={() => navigator.clipboard.writeText(`${window.location.origin}/s/${l.token}`).then(() => toast.success("Link copied"))}
                      >
                        Copy
                      </button>
                      <button type="button" className="text-xs text-destructive hover:underline" onClick={() => revoke(l.token)}>
                        Turn off
                      </button>
                    </>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      <Button variant="outline" onClick={signOut} className="justify-self-start" data-testid="account-sign-out">
        <LogOut /> Sign out
      </Button>

      {me.role !== "owner" && (
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle className="text-destructive">Delete account</CardTitle>
            <CardDescription>Permanently deletes your account, projects, videos and uploads. This can't be undone.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <Field label='Type "DELETE" to confirm' className="flex-1">
              <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} aria-label="Confirm delete" />
            </Field>
            <Button variant="destructive" disabled={confirm !== "DELETE"} onClick={remove}>
              <Trash2 /> Delete my account
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
