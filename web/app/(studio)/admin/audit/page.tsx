"use client";

import { useEffect, useState } from "react";
import { Table } from "@/components/admin/ui";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";

interface Entry {
  id: number;
  ts: string;
  actor_email: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown>;
}

export default function AdminAudit() {
  const [action, setAction] = useState("all");
  const [rows, setRows] = useState<Entry[]>([]);
  useEffect(() => {
    api<Entry[]>(`/admin/audit?limit=300${action === "all" ? "" : `&action=${action}`}`).then(setRows).catch(() => {});
  }, [action]);
  return (
    <div className="grid gap-4">
      <Select
        value={action}
        onValueChange={setAction}
        className="w-56"
        aria-label="Filter actions"
        options={[
          { value: "all", label: "Everything" },
          { value: "user", label: "Users" },
          { value: "tokens", label: "Tokens" },
          { value: "plan", label: "Plans" },
          { value: "upgrade", label: "Upgrades" },
          { value: "settings", label: "Settings" },
          { value: "job", label: "Jobs" },
          { value: "announcement", label: "Announcements" },
        ]}
      />
      <Table head={["When", "Who", "What", "Details"]} testId="audit-table">
        {rows.map((r) => (
          <tr key={r.id} className="align-top">
            <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">{new Date(r.ts).toLocaleString()}</td>
            <td className="px-3 py-2">{r.actor_email ?? "system"}</td>
            <td className="px-3 py-2 font-medium">{r.action}</td>
            <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
              {Object.entries(r.details ?? {})
                .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
                .join("  ")}
            </td>
          </tr>
        ))}
      </Table>
    </div>
  );
}
