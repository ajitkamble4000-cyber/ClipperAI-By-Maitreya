"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Check, Copy, KeyRound, Send, Trash2, Webhook } from "lucide-react";
import { toast } from "sonner";
import { LockedBadge } from "@/components/plan/locked";
import { PageHeader } from "@/components/shell/page-header";
import { hasFeature, useMe } from "@/components/shell/member-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { env } from "@/lib/env";
import { cn, timeAgo } from "@/lib/utils";

interface Key {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
}
interface Delivery {
  event: string;
  status_code: number | null;
  ok: boolean;
  error: string | null;
  created_at: string;
}
interface Hook {
  id: string;
  url: string;
  events: string[];
  active: boolean;
  failures: number;
  last_status: number | null;
  recent: Delivery[];
}

function Secret({ label, value }: { label: string; value: string }) {
  const [done, setDone] = useState(false);
  return (
    <div className="rounded-lg border border-primary/40 bg-primary/5 p-3 text-sm" data-testid="secret-once">
      <p className="mb-1 font-medium">{label}: copy it now, it won&apos;t be shown again</p>
      <div className="flex gap-2">
        <code className="min-w-0 flex-1 truncate rounded bg-background px-2 py-1.5 font-mono text-xs" data-testid="secret-value">
          {value}
        </code>
        <Button size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(value).then(() => setDone(true)).catch(() => {})}>
          {done ? <Check /> : <Copy />}
        </Button>
      </div>
    </div>
  );
}

function Code({ children }: { children: string }) {
  return <pre className="overflow-x-auto rounded-lg border bg-muted/40 p-3 text-xs leading-relaxed">{children}</pre>;
}

export default function DeveloperPage() {
  const me = useMe();
  const allowed = hasFeature(me, "api_access");
  const [keys, setKeys] = useState<Key[]>([]);
  const [hooks, setHooks] = useState<Hook[]>([]);
  const [keyName, setKeyName] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);
  const [hookUrl, setHookUrl] = useState("");
  const [events, setEvents] = useState<string[]>(["job.succeeded", "job.failed"]);
  const [newSecret, setNewSecret] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Key[]>("/api-keys").then(setKeys).catch(() => {});
    api<Hook[]>("/webhooks").then(setHooks).catch(() => {});
  }, []);
  useEffect(load, [load]);

  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    try {
      await fn();
      if (ok) toast.success(ok);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const createKey = () =>
    act(async () => {
      const r = await api<{ key: string }>("/api-keys", { method: "POST", json: { name: keyName.trim() } });
      setNewKey(r.key);
      setKeyName("");
    });
  const createHook = () =>
    act(async () => {
      const r = await api<{ secret: string }>("/webhooks", { method: "POST", json: { url: hookUrl.trim(), events } });
      setNewSecret(r.secret);
      setHookUrl("");
    });
  const testHook = async (h: Hook) => {
    try {
      const r = await api<{ ok: boolean; status: number | null; error: string | null }>(`/webhooks/${h.id}/test`, { method: "POST" });
      if (r.ok) toast.success(`Delivered (HTTP ${r.status})`);
      else toast.error(`Not delivered: ${r.error ?? r.status}`);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const base = env.apiUrl;
  return (
    <div className="grid max-w-4xl gap-6">
      <PageHeader title="Developer API" description="Make clips from your own apps and automations, and get notified when they're done." actions={<LockedBadge feature="api_access" />} />
      {!allowed && (
        <div className="rounded-xl border border-primary/40 bg-primary/5 p-4 text-sm">
          The API and webhooks are part of Business.{" "}
          <Link href="/pricing" className="text-primary underline">
            See plans
          </Link>
          .
        </div>
      )}
      <div className={cn("grid gap-6", !allowed && "pointer-events-none opacity-60")}>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="size-4" /> API keys
            </CardTitle>
            <CardDescription>Send the key in an <code>X-API-Key</code> header. Keys can do what you can, except admin actions and managing keys.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            {newKey && <Secret label="Your new API key" value={newKey} />}
            {keys.map((k) => (
              <div key={k.id} className="flex items-center gap-3 rounded-lg border p-2.5 text-sm" data-testid="api-key-row">
                <span className="font-medium">{k.name}</span>
                <code className="text-xs text-muted-foreground">{k.prefix}…</code>
                <span className="ml-auto text-xs text-muted-foreground">{k.last_used_at ? `used ${timeAgo(k.last_used_at)}` : "never used"}</span>
                <Button size="icon" variant="ghost" aria-label={`Revoke ${k.name}`} onClick={() => act(() => api(`/api-keys/${k.id}`, { method: "DELETE" }), "Key revoked")}>
                  <Trash2 />
                </Button>
              </div>
            ))}
            <div className="flex gap-2">
              <Input value={keyName} onChange={(e) => setKeyName(e.target.value)} placeholder="Key name, e.g. Zapier" aria-label="Key name" maxLength={60} />
              <Button onClick={createKey} disabled={!keyName.trim()} data-testid="create-key">
                Create key
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Webhook className="size-4" /> Webhooks
            </CardTitle>
            <CardDescription>We POST a signed JSON event to your URL when a job finishes, with download links for finished clips.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            {newSecret && <Secret label="Signing secret" value={newSecret} />}
            {hooks.map((h) => (
              <div key={h.id} className="grid gap-2 rounded-lg border p-3 text-sm" data-testid="webhook-row">
                <div className="flex flex-wrap items-center gap-2">
                  <code className="min-w-0 flex-1 truncate text-xs">{h.url}</code>
                  <span className="text-xs text-muted-foreground">{h.events.join(", ")}</span>
                  <Switch checked={h.active} onCheckedChange={(v) => act(() => api(`/webhooks/${h.id}`, { method: "PATCH", json: { active: v } }))} aria-label="Webhook on" />
                  <Button size="sm" variant="outline" onClick={() => testHook(h)} disabled={!h.active} data-testid="test-webhook">
                    <Send /> Test
                  </Button>
                  <Button size="icon" variant="ghost" aria-label="Delete webhook" onClick={() => act(() => api(`/webhooks/${h.id}`, { method: "DELETE" }), "Webhook deleted")}>
                    <Trash2 />
                  </Button>
                </div>
                {h.recent.length > 0 && (
                  <div className="grid gap-0.5 text-xs" data-testid="deliveries">
                    {h.recent.slice(0, 5).map((d, i) => (
                      <span key={i} className={d.ok ? "text-success" : "text-destructive"}>
                        {d.ok ? "✓" : "✗"} {d.event} · {d.status_code ?? d.error} · {timeAgo(d.created_at)}
                      </span>
                    ))}
                  </div>
                )}
                {!h.active && h.failures >= 20 && <p className="text-xs text-destructive">Turned off after 20 failed deliveries. Fix the URL, then switch it back on.</p>}
              </div>
            ))}
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input value={hookUrl} onChange={(e) => setHookUrl(e.target.value)} placeholder="https://example.com/webhooks/shorts" aria-label="Webhook URL" />
              <div className="flex items-center gap-3 text-xs">
                {["job.succeeded", "job.failed"].map((ev) => (
                  <label key={ev} className="flex items-center gap-1">
                    <input type="checkbox" checked={events.includes(ev)} onChange={() => setEvents((x) => (x.includes(ev) ? x.filter((y) => y !== ev) : [...x, ev]))} />
                    {ev}
                  </label>
                ))}
              </div>
              <Button onClick={createHook} disabled={!hookUrl.trim() || !events.length} data-testid="create-webhook">
                Add webhook
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quick start</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm">
            <p>1. Start a job from any link (same options as the app):</p>
            <Code>{`curl -X POST ${base}/clipper/projects \\
  -H "X-API-Key: $SHORTS_KEY" -H "Content-Type: application/json" \\
  -d '{"url": "https://www.youtube.com/watch?v=...", "mode": "auto", "aspect": "9:16",
       "caption_style": {"preset": "bold_pop"}}'
# → {"project_id": "...", "job_id": "...", "tokens": 250}`}</Code>
            <p>2. Check progress (or use a webhook):</p>
            <Code>{`curl ${base}/jobs/JOB_ID -H "X-API-Key: $SHORTS_KEY"
# → {"status": "running", "percent": 42, ...}`}</Code>
            <p>3. Get the finished clips with download links (valid 24 hours):</p>
            <Code>{`curl ${base}/projects/PROJECT_ID/clips -H "X-API-Key: $SHORTS_KEY"`}</Code>
            <p>Check a webhook signature (Node.js):</p>
            <Code>{`const crypto = require("crypto");
const expected = "sha256=" + crypto.createHmac("sha256", SIGNING_SECRET).update(rawBody).digest("hex");
const ok = crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(req.headers["x-studio-signature"]));`}</Code>
            <p>Python:</p>
            <Code>{`import hmac, hashlib
expected = "sha256=" + hmac.new(SIGNING_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
ok = hmac.compare_digest(expected, request.headers["X-Studio-Signature"])`}</Code>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
