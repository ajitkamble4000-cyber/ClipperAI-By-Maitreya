"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { STATUS_COLOR, Table } from "@/components/admin/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";

export interface AdminUser {
  user_id: string;
  email: string;
  role: "owner" | "admin" | "user";
  display_name: string | null;
  plan_id: string;
  team: "staff" | "creator" | null;
  status: "active" | "suspended";
  suspended_reason: string | null;
  created_at: string;
  last_seen_at: string | null;
  projects: number;
}

const ALL = "all";

export default function AdminUsers() {
  const [q, setQ] = useState("");
  const [plan, setPlan] = useState(ALL);
  const [team, setTeam] = useState(ALL);
  const [role, setRole] = useState(ALL);
  const [state, setState] = useState(ALL);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ total: number; users: AdminUser[] } | null>(null);

  useEffect(() => {
    const p = new URLSearchParams({ page: String(page), per_page: "50" });
    if (q.trim()) p.set("q", q.trim());
    if (plan !== ALL) p.set("plan", plan);
    if (team !== ALL) p.set("team", team);
    if (role !== ALL) p.set("role", role);
    if (state !== ALL) p.set("status", state);
    const t = setTimeout(() => api<{ total: number; users: AdminUser[] }>(`/admin/users?${p}`).then(setData).catch(() => {}), 250);
    return () => clearTimeout(t);
  }, [q, plan, team, role, state, page]);

  return (
    <div className="grid gap-4">
      <div className="grid gap-2 sm:grid-cols-[1fr_repeat(4,140px)]">
        <Input placeholder="Search name or email" value={q} onChange={(e) => (setQ(e.target.value), setPage(1))} aria-label="Search users" />
        <Select value={plan} onValueChange={(v) => (setPlan(v), setPage(1))} aria-label="Plan" options={[{ value: ALL, label: "All plans" }, { value: "free", label: "Free" }, { value: "pro", label: "Pro" }, { value: "business", label: "Business" }, { value: "team", label: "Team" }]} />
        <Select value={team} onValueChange={(v) => (setTeam(v), setPage(1))} aria-label="Team" options={[{ value: ALL, label: "Any team" }, { value: "staff", label: "Staff" }, { value: "creator", label: "Creators" }, { value: "none", label: "No team" }]} />
        <Select value={role} onValueChange={(v) => (setRole(v), setPage(1))} aria-label="Role" options={[{ value: ALL, label: "Any role" }, { value: "owner", label: "Owner" }, { value: "admin", label: "Admin" }, { value: "user", label: "User" }]} />
        <Select value={state} onValueChange={(v) => (setState(v), setPage(1))} aria-label="Status" options={[{ value: ALL, label: "Any status" }, { value: "active", label: "Active" }, { value: "suspended", label: "Suspended" }]} />
      </div>
      <p className="text-sm text-muted-foreground">{data ? `${data.total.toLocaleString()} user${data.total === 1 ? "" : "s"}` : "Loading…"}</p>
      <Table head={["User", "Plan", "Team", "Role", "Status", "Projects", "Last seen", "Joined"]} testId="users-table">
        {data?.users.map((u) => (
          <tr key={u.user_id} className="hover:bg-muted/30">
            <td className="px-3 py-2">
              <Link href={`/admin/users/${u.user_id}`} className="block hover:text-primary">
                <span className="block font-medium">{u.display_name ?? u.email.split("@")[0]}</span>
                <span className="block text-xs text-muted-foreground">{u.email}</span>
              </Link>
            </td>
            <td className="px-3 py-2 capitalize">{u.plan_id}</td>
            <td className="px-3 py-2 capitalize">{u.team ?? "–"}</td>
            <td className="px-3 py-2 capitalize">{u.role}</td>
            <td className={cn("px-3 py-2 capitalize", STATUS_COLOR[u.status])}>{u.status}</td>
            <td className="px-3 py-2 tabular-nums">{u.projects}</td>
            <td className="px-3 py-2 text-muted-foreground">{u.last_seen_at ? timeAgo(u.last_seen_at) : "never"}</td>
            <td className="px-3 py-2 text-muted-foreground">{new Date(u.created_at).toLocaleDateString()}</td>
          </tr>
        ))}
      </Table>
      {data && data.total > 50 && (
        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {Math.ceil(data.total / 50)}
          </span>
          <Button variant="outline" size="sm" disabled={page * 50 >= data.total} onClick={() => setPage((p) => p + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
