"use client";

import { useCallback, useEffect, useState } from "react";
import { Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { useMe } from "@/components/shell/member-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/utils";

interface MemberRow {
  user_id: string;
  email: string;
  role: "admin" | "member";
  display_name: string | null;
  created_at: string;
}
interface InviteRow {
  id: string;
  email: string;
  role: string;
  created_at: string;
}

export function MembersTab() {
  const me = useMe();
  const admin = me.role === "admin";
  const [members, setMembers] = useState<MemberRow[]>([]);
  const [invites, setInvites] = useState<InviteRow[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<MemberRow[]>("/members").then(setMembers).catch((e) => toast.error(e.message));
    if (admin) api<InviteRow[]>("/invites").then(setInvites).catch(() => {});
  }, [admin]);
  useEffect(load, [load]);

  const invite = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/invites", { method: "POST", json: { email, role } });
      toast.success(`Invite sent to ${email}`);
      setEmail("");
      load();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      toast.success(ok);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="grid max-w-3xl gap-6">
      {admin && (
        <Card>
          <CardHeader>
            <CardTitle>Invite a teammate</CardTitle>
            <CardDescription>They get an email with a link to set their password. There is no public sign-up.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={invite} className="flex flex-col gap-2 sm:flex-row">
              <Input type="email" required placeholder="name@company.com" value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Invite email" />
              <Select
                value={role}
                onValueChange={setRole}
                className="sm:w-36"
                options={[
                  { value: "member", label: "Member" },
                  { value: "admin", label: "Admin" },
                ]}
              />
              <Button disabled={busy}>
                <UserPlus /> Invite
              </Button>
            </form>
            {invites.length > 0 && (
              <div className="mt-4 grid gap-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Pending invites</p>
                {invites.map((i) => (
                  <div key={i.id} className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
                    <span className="truncate">
                      {i.email} <span className="text-muted-foreground">· {i.role} · {timeAgo(i.created_at)}</span>
                    </span>
                    <Button size="sm" variant="ghost" onClick={() => act(() => api(`/invites/${i.id}`, { method: "DELETE" }), "Invite revoked")}>
                      Revoke
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Members ({members.length})</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2">
          {members.map((m) => (
            <div key={m.user_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {m.display_name ?? m.email} {m.user_id === me.user_id && <span className="text-muted-foreground">(you)</span>}
                </p>
                <p className="truncate text-xs text-muted-foreground">{m.email}</p>
              </div>
              {admin && m.user_id !== me.user_id ? (
                <div className="flex items-center gap-2">
                  <Select
                    value={m.role}
                    className="h-8 w-28"
                    onValueChange={(r) => act(() => api(`/members/${m.user_id}`, { method: "PATCH", json: { role: r } }), "Role updated")}
                    options={[
                      { value: "member", label: "Member" },
                      { value: "admin", label: "Admin" },
                    ]}
                  />
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={`Remove ${m.email}`}
                    onClick={() => confirm(`Remove ${m.email} from the workspace?`) && act(() => api(`/members/${m.user_id}`, { method: "DELETE" }), "Member removed")}
                  >
                    <Trash2 />
                  </Button>
                </div>
              ) : (
                <Badge variant={m.role === "admin" ? "default" : "secondary"} className="capitalize">
                  {m.role}
                </Badge>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
