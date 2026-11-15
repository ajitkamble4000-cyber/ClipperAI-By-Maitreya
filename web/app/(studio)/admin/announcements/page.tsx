"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/utils";

interface Ann {
  id: string;
  message: string;
  level: string;
  active: boolean;
  expires_at: string | null;
  created_at: string;
}

export default function AdminAnnouncements() {
  const [rows, setRows] = useState<Ann[]>([]);
  const [msg, setMsg] = useState("");
  const [level, setLevel] = useState("info");
  const [until, setUntil] = useState("");
  const load = useCallback(() => api<Ann[]>("/admin/announcements").then(setRows).catch(() => {}), []);
  useEffect(() => {
    load();
  }, [load]);

  const post = async () => {
    try {
      await api("/admin/announcements", { method: "POST", json: { message: msg, level, expires_at: until ? new Date(until).toISOString() : null } });
      setMsg("");
      toast.success("Announcement is live on everyone's Home");
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="grid max-w-3xl gap-6">
      <Card>
        <CardHeader>
          <CardTitle>New announcement</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <Textarea rows={2} value={msg} onChange={(e) => setMsg(e.target.value)} maxLength={500} placeholder="New: 16:9 output for YouTube is here!" aria-label="Announcement" />
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <Field label="Type" className="sm:w-40">
              <Select value={level} onValueChange={setLevel} options={[{ value: "info", label: "Info" }, { value: "success", label: "Good news" }, { value: "warning", label: "Warning" }]} />
            </Field>
            <Field label="Show until (optional)" className="sm:w-56">
              <Input type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)} aria-label="Show until" />
            </Field>
            <Button onClick={post} disabled={msg.trim().length < 3} className="sm:ml-auto" data-testid="post-announcement">
              Publish
            </Button>
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-2">
        {rows.map((a) => (
          <div key={a.id} className="flex items-start gap-3 rounded-xl border p-3 text-sm">
            <span className="min-w-0 flex-1">
              {a.message}
              <span className="block text-xs text-muted-foreground">
                {a.level} · {timeAgo(a.created_at)}
                {a.expires_at ? ` · until ${new Date(a.expires_at).toLocaleString()}` : ""}
              </span>
            </span>
            {a.active ? (
              <Button size="sm" variant="outline" onClick={() => api(`/admin/announcements/${a.id}`, { method: "DELETE" }).then(load)}>
                End
              </Button>
            ) : (
              <span className="text-xs text-muted-foreground">ended</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
