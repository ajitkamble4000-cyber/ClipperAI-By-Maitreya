"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { STATUS_COLOR } from "@/components/admin/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";

interface Req {
  id: string;
  user_id: string;
  email: string;
  display_name: string | null;
  plan_id: string;
  plan_name: string;
  current_plan: string;
  note: string;
  status: string;
  reply: string;
  created_at: string;
}

export default function AdminRequests() {
  const [state, setState] = useState("pending");
  const [rows, setRows] = useState<Req[] | null>(null);
  const [reply, setReply] = useState<Record<string, string>>({});
  const load = useCallback(() => api<Req[]>(`/admin/upgrade-requests?state=${state}`).then(setRows).catch(() => setRows([])), [state]);
  useEffect(() => {
    load();
  }, [load]);

  const decide = async (r: Req, approve: boolean) => {
    try {
      await api(`/admin/upgrade-requests/${r.id}`, { method: "POST", json: { approve, reply: reply[r.id] ?? "" } });
      toast.success(approve ? `${r.display_name ?? r.email} is on ${r.plan_name} now` : "Request declined");
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Approving switches the user's plan right away and notifies them.</p>
        <Select
          value={state}
          onValueChange={setState}
          className="w-40"
          aria-label="Request status"
          options={[
            { value: "pending", label: "Waiting" },
            { value: "approved", label: "Approved" },
            { value: "declined", label: "Declined" },
            { value: "all", label: "All" },
          ]}
        />
      </div>
      {rows?.length === 0 && <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">Nothing here.</p>}
      {rows?.map((r) => (
        <div key={r.id} className="grid gap-3 rounded-xl border p-4" data-testid="upgrade-request">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Link href={`/admin/users/${r.user_id}`} className="font-medium hover:text-primary">
              {r.display_name ?? r.email}
            </Link>
            <span className="text-muted-foreground">
              {r.current_plan} → <b className="text-foreground">{r.plan_name}</b> · {timeAgo(r.created_at)}
            </span>
            <span className={cn("ml-auto capitalize", STATUS_COLOR[r.status])}>{r.status}</span>
          </div>
          {r.note && <p className="text-sm text-muted-foreground">“{r.note}”</p>}
          {r.status === "pending" ? (
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                placeholder="Reply (optional, shown to them)"
                value={reply[r.id] ?? ""}
                onChange={(e) => setReply((x) => ({ ...x, [r.id]: e.target.value }))}
                aria-label="Reply"
                maxLength={500}
              />
              <Button onClick={() => decide(r, true)} data-testid="approve">
                Approve
              </Button>
              <Button variant="outline" onClick={() => decide(r, false)}>
                Decline
              </Button>
            </div>
          ) : (
            r.reply && <p className="text-xs text-muted-foreground">Reply: {r.reply}</p>
          )}
        </div>
      ))}
    </div>
  );
}
