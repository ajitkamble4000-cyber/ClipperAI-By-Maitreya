"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCcw } from "lucide-react";
import { toast } from "sonner";
import { STATUS_COLOR, Table } from "@/components/admin/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import { href } from "@/lib/routes";

interface Job {
  id: string;
  kind: string;
  status: string;
  percent: number;
  message: string | null;
  error: string | null;
  tokens_charged: number;
  project_id: string | null;
  project_title: string | null;
  project_type: string | null;
  user_name: string | null;
  created_at: string;
  seconds: number;
}

export default function AdminJobs() {
  const [state, setState] = useState("all");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Job[] | null>(null);
  const load = useCallback(() => {
    const p = new URLSearchParams({ limit: "150" });
    if (state !== "all") p.set("status", state);
    if (q.trim()) p.set("q", q.trim());
    api<Job[]>(`/admin/jobs?${p}`).then(setRows).catch(() => setRows([]));
  }, [state, q]);
  useEffect(() => {
    const t = setTimeout(load, 250);
    const id = setInterval(load, 10_000);
    return () => (clearTimeout(t), clearInterval(id));
  }, [load]);

  const cancel = async (j: Job) => {
    try {
      const r = await api<{ refunded: number }>(`/admin/jobs/${j.id}/cancel`, { method: "POST" });
      toast.success(`Canceled${r.refunded ? `, ${r.refunded} tokens refunded` : ""}`);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const refund = async (j: Job) => {
    const reason = prompt(`Refund ${j.tokens_charged} tokens to ${j.user_name ?? "this user"}? Optional note for them:`, "");
    if (reason === null) return;
    try {
      const r = await api<{ refunded: number }>(`/admin/jobs/${j.id}/refund`, { method: "POST", json: { reason } });
      toast.success(`${r.refunded} tokens refunded`);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="grid gap-4">
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input placeholder="Search user email or project" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search jobs" />
        <Select
          value={state}
          onValueChange={setState}
          className="sm:w-44"
          aria-label="Job status"
          options={[
            { value: "all", label: "All jobs" },
            { value: "active", label: "Running & queued" },
            { value: "failed", label: "Failed" },
            { value: "succeeded", label: "Succeeded" },
            { value: "canceled", label: "Canceled" },
          ]}
        />
        <Button variant="outline" onClick={load} aria-label="Refresh">
          <RefreshCcw />
        </Button>
      </div>
      <Table head={["Job", "User", "Project", "Status", "Tokens", "Time", "Started", ""]} testId="jobs-table">
        {rows?.map((j) => (
          <tr key={j.id} className="align-top">
            <td className="px-3 py-2">{j.kind.replace(/_/g, " ")}</td>
            <td className="px-3 py-2">{j.user_name ?? "–"}</td>
            <td className="max-w-48 px-3 py-2">
              {j.project_id ? (
                <Link href={href(`/${j.project_type === "story" ? "story" : "clipper"}/${j.project_id}`)} className="line-clamp-1 hover:text-primary">
                  {j.project_title ?? "Project"}
                </Link>
              ) : (
                "–"
              )}
            </td>
            <td className="px-3 py-2">
              <span className={cn("capitalize", STATUS_COLOR[j.status])}>{j.status}</span>
              {j.status === "running" && <span className="text-xs text-muted-foreground"> {j.percent}%</span>}
              {j.error && <p className="line-clamp-2 max-w-64 text-xs text-destructive">{j.error}</p>}
            </td>
            <td className="px-3 py-2 tabular-nums">{j.tokens_charged}</td>
            <td className="px-3 py-2 tabular-nums text-muted-foreground">{Math.round(j.seconds)} s</td>
            <td className="px-3 py-2 text-muted-foreground">{timeAgo(j.created_at)}</td>
            <td className="px-3 py-2">
              {["queued", "running"].includes(j.status) ? (
                <Button size="sm" variant="outline" onClick={() => cancel(j)}>
                  Cancel
                </Button>
              ) : j.tokens_charged > 0 ? (
                <Button size="sm" variant="outline" onClick={() => refund(j)} data-testid="refund-job">
                  Refund
                </Button>
              ) : null}
            </td>
          </tr>
        ))}
      </Table>
    </div>
  );
}
