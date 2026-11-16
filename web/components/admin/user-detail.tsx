"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Ban, Coins, Crown, ShieldCheck, ShieldOff, Trash2, UserCheck } from "lucide-react";
import { toast } from "sonner";
import type { AdminUser } from "@/app/(studio)/admin/users/page";
import { STATUS_COLOR, Stat } from "@/components/admin/ui";
import { useMe } from "@/components/shell/member-context";
import type { Wallet } from "@/components/shell/token-chip";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";

interface Detail extends AdminUser {
  recent_projects: { id: string; type: "clip" | "story"; title: string; status: string; created_at: string }[];
  recent_jobs: { id: string; kind: string; status: string; error: string | null; created_at: string }[];
}
interface Ledger {
  id: number;
  ts: string;
  delta: number;
  reason: string;
  action: string | null;
  meta: Record<string, unknown>;
  project_title: string | null;
}

export function AdminUserDetail({ id }: { id: string }) {
  const me = useMe();
  const router = useRouter();
  const [u, setU] = useState<Detail | null>(null);
  const [w, setW] = useState<{ wallet: Wallet; ledger: Ledger[] } | null>(null);
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [daily, setDaily] = useState("");
  const [reason, setReason] = useState("");

  const load = useCallback(() => {
    api<Detail>(`/admin/users/${id}`).then(setU).catch((e) => toast.error((e as Error).message));
    api<{ wallet: Wallet; ledger: Ledger[] }>(`/admin/users/${id}/tokens`).then(setW).catch(() => {});
  }, [id]);
  useEffect(load, [load]);

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    try {
      await fn();
      toast.success(msg);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const patch = (body: Record<string, unknown>, msg: string) => act(() => api(`/admin/users/${id}`, { method: "PATCH", json: body }), msg);

  if (!u) return null;
  const isSelf = u.user_id === me.user_id;
  const protectedTarget = (u.role === "owner" || u.role === "admin") && me.role !== "owner" && !isSelf;

  return (
    <div className="grid gap-6">
      <Link href="/admin/users" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Users
      </Link>
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-semibold" data-testid="user-name">
            {u.display_name ?? u.email}
            {u.role === "owner" && <Crown className="size-4 text-primary" aria-label="Owner" />}
            {u.role === "admin" && <ShieldCheck className="size-4 text-primary" aria-label="Admin" />}
          </h2>
          <p className="text-sm text-muted-foreground">
            {u.email} · joined {new Date(u.created_at).toLocaleDateString()} · last seen {u.last_seen_at ? timeAgo(u.last_seen_at) : "never"}
          </p>
        </div>
        <span className={cn("ml-auto rounded-full border px-3 py-1 text-sm capitalize", STATUS_COLOR[u.status])} data-testid="user-status">
          {u.status}
        </span>
      </div>
      {u.status === "suspended" && u.suspended_reason && <p className="text-sm text-destructive">Suspended: {u.suspended_reason}</p>}
      {protectedTarget && <p className="rounded-lg border p-3 text-sm text-muted-foreground">Only the owner can change admins and the owner account.</p>}

      <div className={cn("grid gap-6 lg:grid-cols-2", protectedTarget && "pointer-events-none opacity-60")}>
        <Card>
          <CardHeader>
            <CardTitle>Plan & team</CardTitle>
            <CardDescription>Staff and Creator team members get everything free and unlimited.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field label="Plan">
              <Select
                value={u.plan_id}
                aria-label="User plan"
                onValueChange={(v) => patch({ plan_id: v }, `Plan changed to ${v}`)}
                options={[
                  { value: "free", label: "Free" },
                  { value: "pro", label: "Pro" },
                  { value: "business", label: "Business" },
                  { value: "team", label: "Team (unlimited)" },
                ]}
              />
            </Field>
            <Field label="Team">
              <Select
                value={u.team ?? "none"}
                aria-label="User team"
                onValueChange={(v) => patch({ team: v }, v === "none" ? "Removed from the team" : `Added to the ${v} team`)}
                options={[
                  { value: "none", label: "No team" },
                  { value: "staff", label: "Staff team (free)" },
                  { value: "creator", label: "Content creator team (free)" },
                ]}
              />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Coins className="size-4" /> Tokens
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            {w && (
              <div className="grid grid-cols-3 gap-2">
                <Stat label="Total" value={w.wallet.unlimited ? "∞" : w.wallet.total.toLocaleString()} testId="user-tokens" />
                <Stat label="Daily" value={w.wallet.unlimited ? "∞" : `${w.wallet.daily_balance}/${w.wallet.daily_allowance}`} />
                <Stat label="Bonus" value={w.wallet.bonus_balance.toLocaleString()} />
              </div>
            )}
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <Field label="Give or take bonus tokens" className="sm:w-36">
                <Input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="e.g. 500 or -200" aria-label="Token amount" />
              </Field>
              <Field label="Note (shown to them)" className="flex-1">
                <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} placeholder="Thanks for the feedback!" aria-label="Token note" />
              </Field>
              <Button
                disabled={!amount || Number(amount) === 0}
                data-testid="grant-tokens"
                onClick={() =>
                  act(
                    () => api(`/admin/users/${id}/tokens`, { method: "POST", json: { amount: Number(amount), note } }),
                    Number(amount) > 0 ? `Gave ${Number(amount).toLocaleString()} tokens` : `Took ${Math.abs(Number(amount)).toLocaleString()} tokens`,
                  ).then(() => (setAmount(""), setNote("")))
                }
              >
                Apply
              </Button>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <Field label="Custom daily allowance" hint="Leave empty to use the plan's" className="flex-1">
                <Input type="number" min={0} value={daily} onChange={(e) => setDaily(e.target.value)} placeholder={`Plan default`} aria-label="Daily allowance" />
              </Field>
              <Button variant="outline" onClick={() => act(() => api(`/admin/users/${id}/daily-tokens`, { method: "PUT", json: { daily_tokens: daily === "" ? null : Number(daily) } }), "Daily allowance updated")}>
                Save allowance
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Access</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            {u.status === "active" ? (
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                <Field label="Reason (shown to them)" className="flex-1">
                  <Input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} placeholder="Breaking the rules" aria-label="Suspend reason" />
                </Field>
                <Button variant="destructive" disabled={isSelf} onClick={() => patch({ status: "suspended", suspended_reason: reason || "Suspended by an admin" }, "User suspended")} data-testid="suspend">
                  <Ban /> Suspend
                </Button>
              </div>
            ) : (
              <Button onClick={() => patch({ status: "active" }, "User reactivated")} className="justify-self-start" data-testid="reactivate">
                <UserCheck /> Reactivate
              </Button>
            )}
            {me.role === "owner" && u.role !== "owner" && (
              <Button
                variant="outline"
                className="justify-self-start"
                data-testid="toggle-admin"
                onClick={() => act(() => api(`/admin/users/${id}/role`, { method: "PUT", json: { role: u.role === "admin" ? "user" : "admin" } }), u.role === "admin" ? "Admin removed" : "Now an admin")}
              >
                {u.role === "admin" ? <ShieldOff /> : <ShieldCheck />} {u.role === "admin" ? "Remove admin" : "Make admin"}
              </Button>
            )}
            {!isSelf && u.role !== "owner" && (
              <Button
                variant="ghost"
                className="justify-self-start text-destructive"
                onClick={() => {
                  if (!confirm(`Delete ${u.email} and everything they made? This can't be undone.`)) return;
                  act(() => api(`/admin/users/${id}`, { method: "DELETE" }), "User deleted").then(() => router.push("/admin/users"));
                }}
              >
                <Trash2 /> Delete user
              </Button>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-1.5 text-sm">
            {u.recent_jobs.length === 0 && <p className="text-muted-foreground">No jobs yet.</p>}
            {u.recent_jobs.slice(0, 10).map((j) => (
              <div key={j.id} className="flex justify-between gap-2">
                <span className="truncate">{j.kind.replace(/_/g, " ")}</span>
                <span className={cn("capitalize", STATUS_COLOR[j.status])}>{j.status}</span>
                <span className="text-xs text-muted-foreground">{timeAgo(j.created_at)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {w && w.ledger.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Token history</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-1 text-sm">
            {w.ledger.slice(0, 30).map((l) => (
              <div key={l.id} className="flex gap-3">
                <span className="w-36 shrink-0 text-xs text-muted-foreground">{new Date(l.ts).toLocaleString()}</span>
                <span className="flex-1 truncate">
                  {l.reason}
                  {l.action ? ` · ${l.action}` : ""}
                  {l.project_title ? ` · ${l.project_title}` : ""}
                </span>
                <span className={cn("tabular-nums", l.delta > 0 && "text-success")}>{l.delta > 0 ? `+${l.delta}` : l.delta}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
