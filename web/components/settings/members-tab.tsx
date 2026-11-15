"use client";

import { useCallback, useEffect, useState } from "react";
import { UserPlus } from "lucide-react";
import { toast } from "sonner";
import { isAdmin, useMe } from "@/components/shell/member-context";
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
  role: "owner" | "admin" | "user";
  display_name: string | null;
  team: string | null;
  created_at: string;
}
interface InviteRow {
  id: string;
  email: string;
  role: string;
  team: string | null;
  created_at: string;
}

/** Team & invites. Admins invite people (optionally straight into the Staff/Creator team); only the owner invites admins. */
export function MembersTab() {
  const me = useMe();
  const admin = isAdmin(me);
  const [members, setMembers] = useState<MemberRow[]>([]);
  const [invites, setInvites] = useState<InviteRow[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("user");
  const [team, setTeam] = useState("none");
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
      await api("/invites", { method: "POST", json: { email, role, team: team === "none" ? null : team } });
      toast.success(`Invite sent to ${email}`);
      setEmail("");
      load();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const shown = admin ? members.filter((m) => m.team || m.role !== "user") : members;

  return (
    <div className="grid max-w-3xl gap-6">
      {admin && (
        <Card>
          <CardHeader>
            <CardTitle>Invite someone</CardTitle>
            <CardDescription>
              Anyone can sign up on their own. Invite people to put them straight into the Staff or Creator team (everything free)
              {me.role === "owner" ? " or to make them an admin" : ""}.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={invite} className="grid gap-2 sm:grid-cols-[1fr_140px_150px_auto]">
              <Input type="email" required placeholder="name@company.com" value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Invite email" />
              <Select
                value={team}
                onValueChange={setTeam}
                options={[
                  { value: "none", label: "No team" },
                  { value: "staff", label: "Staff team" },
                  { value: "creator", label: "Creator team" },
                ]}
              />
              <Select
                value={role}
                onValueChange={setRole}
                disabled={me.role !== "owner"}
                options={[
                  { value: "user", label: "User" },
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
                      {i.email}{" "}
                      <span className="text-muted-foreground">
                        · {i.role}
                        {i.team ? ` · ${i.team} team` : ""} · {timeAgo(i.created_at)}
                      </span>
                    </span>
                    <Button size="sm" variant="ghost" onClick={() => api(`/invites/${i.id}`, { method: "DELETE" }).then(load)}>
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
          <CardTitle>{admin ? "Admins & team" : me.team ? "Your team" : "Your account"}</CardTitle>
          {admin && <CardDescription>Manage everyone else in Admin → Users.</CardDescription>}
        </CardHeader>
        <CardContent className="grid gap-2">
          {shown.map((m) => (
            <div key={m.user_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {m.display_name ?? m.email} {m.user_id === me.user_id && <span className="text-muted-foreground">(you)</span>}
                </p>
                <p className="truncate text-xs text-muted-foreground">{m.email}</p>
              </div>
              <div className="flex gap-1">
                {m.team && <Badge variant="secondary" className="capitalize">{m.team}</Badge>}
                <Badge variant={m.role === "user" ? "secondary" : "default"} className="capitalize">
                  {m.role}
                </Badge>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
