"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { env } from "@/lib/env";
import { api } from "@/lib/api";
import { supabaseBrowser } from "@/lib/supabase/client";
import { useSettings, type SettingsView } from "./ai-tab";

export function DownloadsTab() {
  const { s, setS, load } = useSettings();
  const [proxy, setProxy] = useState("");
  const [days, setDays] = useState<string>("");
  const file = useRef<HTMLInputElement>(null);
  if (!s) return null;

  const uploadCookies = async (f: File) => {
    const body = new FormData();
    body.append("file", f);
    const { data } = await supabaseBrowser().auth.getSession();
    const res = await fetch(`${env.apiUrl}/settings/cookies`, {
      method: "POST",
      body,
      headers: { Authorization: `Bearer ${data.session?.access_token ?? ""}` },
    });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) return toast.error(j.detail ?? "Upload failed");
    toast.success(`cookies.txt saved (${j.cookies} cookies)`);
    load();
  };

  return (
    <div className="grid max-w-3xl gap-6">
      <Card>
        <CardHeader>
          <CardTitle>YouTube downloads</CardTitle>
          <CardDescription>
            YouTube often blocks downloads from server IPs ("Sign in to confirm you're not a bot"). A cookies.txt from a logged-in
            browser, and/or a residential proxy, usually fixes it. Uploading the video file always works.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5">
          <div className="grid gap-2">
            <div className="flex items-center gap-2 text-sm font-medium">
              cookies.txt {s.cookies_set ? <Badge variant="success">Set</Badge> : <Badge variant="secondary">Not set</Badge>}
            </div>
            <p className="text-xs text-muted-foreground">
              Use a separate Google account, export cookies for youtube.com in Netscape format, and upload here. Stored encrypted.
            </p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => file.current?.click()}>
                Upload cookies.txt
              </Button>
              {s.cookies_set && (
                <Button variant="ghost" onClick={() => api("/settings/cookies", { method: "DELETE" }).then(load)}>
                  Remove
                </Button>
              )}
            </div>
            <input ref={file} type="file" accept=".txt,text/plain" hidden onChange={(e) => e.target.files?.[0] && uploadCookies(e.target.files[0])} />
          </div>
          <div className="grid gap-2">
            <div className="flex items-center gap-2 text-sm font-medium">
              Proxy {s.proxy_set ? <Badge variant="success">Set</Badge> : <Badge variant="secondary">Not set</Badge>}
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input type="password" autoComplete="off" placeholder="http://user:pass@host:port or socks5://host:port" value={proxy} onChange={(e) => setProxy(e.target.value)} aria-label="Proxy URL" />
              <Button
                variant="outline"
                disabled={!proxy}
                onClick={() =>
                  api("/settings/proxy", { method: "PUT", json: { url: proxy } })
                    .then(() => {
                      setProxy("");
                      toast.success("Proxy saved");
                      load();
                    })
                    .catch((e) => toast.error(e.message))
                }
              >
                Save
              </Button>
              {s.proxy_set && (
                <Button variant="ghost" onClick={() => api("/settings/proxy", { method: "PUT", json: { url: null } }).then(load)}>
                  Remove
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Storage</CardTitle>
          <CardDescription>Uploaded and downloaded source videos are deleted after this many days. Finished clips and stories are kept.</CardDescription>
        </CardHeader>
        <CardContent className="flex items-end gap-2">
          <Field label="Delete sources after (days)" className="w-56">
            <Input type="number" min={1} max={365} placeholder={String(s.source_retention_days)} value={days} onChange={(e) => setDays(e.target.value)} />
          </Field>
          <Button
            disabled={!days}
            onClick={() =>
              api<SettingsView>("/settings", { method: "PUT", json: { source_retention_days: Number(days) } })
                .then((v) => {
                  setS(v);
                  setDays("");
                  toast.success("Saved");
                })
                .catch((e) => toast.error(e.message))
            }
          >
            Save
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
