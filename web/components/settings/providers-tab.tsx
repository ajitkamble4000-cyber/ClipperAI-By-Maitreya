"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, KeyRound, Plus, RefreshCw, X, XCircle } from "lucide-react";
import { toast } from "sonner";
import { useMe } from "@/components/shell/member-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";

interface Provider {
  id: string;
  label: string;
  roles: string[];
  docs: string;
  needs_base_url: boolean;
  base_url: string | null;
  enabled: boolean;
  configured: boolean;
  key_masked: string | null;
  source: "env" | "vault" | "none";
  vision: boolean;
  video_input: boolean;
}

interface ModelOpt {
  name: string;
  label: string;
}

const ROLES: { id: string; label: string; hint: string; fallback?: boolean }[] = [
  { id: "text", label: "Text & analysis", hint: "Scripts, finding moments, titles, translation", fallback: true },
  { id: "image", label: "Images", hint: "Scene images, characters, thumbnails", fallback: true },
  { id: "tts", label: "Voice", hint: "AI narration", fallback: true },
  { id: "video", label: "AI video", hint: "Premium image-to-video" },
  { id: "transcribe", label: "Transcription", hint: "Speech to text with word timing" },
];

function ProviderCard({ p, owner, onSaved }: { p: Provider; owner: boolean; onSaved: () => void }) {
  const [key, setKey] = useState("");
  const [base, setBase] = useState(p.base_url ?? "");
  const [busy, setBusy] = useState(false);
  const save = async (body: Record<string, unknown>, msg: string) => {
    setBusy(true);
    try {
      await api(`/settings/providers/${p.id}`, { method: "PUT", json: body });
      toast.success(msg);
      setKey("");
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const test = async () => {
    const r = await api<{ ok: boolean; error?: string; models?: number }>(`/settings/providers/${p.id}/test`, { method: "POST" }).catch(
      (e: Error) => ({ ok: false, error: e.message }) as { ok: boolean; error?: string; models?: number },
    );
    if (r.ok) toast.success(`${p.label}: works (${r.models} models)`);
    else toast.error(r.error ?? "Test failed");
  };
  if (p.id === "local") return null;
  return (
    <div className="grid gap-3 rounded-xl border p-4" data-testid={`provider-${p.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{p.label}</p>
          <p className="text-xs text-muted-foreground">{p.roles.join(" · ")}{p.vision ? " · sees images" : ""}{p.video_input ? " · watches video" : ""}</p>
        </div>
        <div className="flex items-center gap-2">
          {p.configured ? (
            <Badge variant="success"><CheckCircle2 className="size-3" /> {p.key_masked ?? "ready"}{p.source === "env" ? " (env)" : ""}</Badge>
          ) : (
            <Badge variant="secondary"><XCircle className="size-3" /> no key</Badge>
          )}
          {owner && (
            <Switch checked={p.enabled} onCheckedChange={(v) => save({ enabled: v }, v ? "Enabled" : "Disabled")} aria-label={`Enable ${p.label}`} />
          )}
        </div>
      </div>
      {owner && (
        <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
          {p.needs_base_url && (
            <Input className="sm:col-span-3" placeholder="Base URL, e.g. https://api.groq.com/openai/v1" value={base} onChange={(e) => setBase(e.target.value)} aria-label={`${p.label} base URL`} />
          )}
          <Input type="password" autoComplete="off" placeholder={p.configured ? "Replace key" : "Paste API key"} value={key} onChange={(e) => setKey(e.target.value)} aria-label={`${p.label} API key`} />
          <Button disabled={busy || (!key && !(p.needs_base_url && base !== (p.base_url ?? "")))} onClick={() => save({ key: key || null, base_url: p.needs_base_url ? base : null }, "Saved and tested")}>
            <KeyRound /> Save & test
          </Button>
          <div className="flex gap-1">
            {p.configured && <Button variant="outline" onClick={test}>Test</Button>}
            {p.source === "vault" && (
              <Button variant="ghost" size="icon" aria-label={`Remove ${p.label} key`} onClick={() => confirm(`Remove the ${p.label} key?`) && save({ clear_key: true }, "Key removed")}>
                <X />
              </Button>
            )}
          </div>
        </div>
      )}
      {p.docs && (
        <a href={p.docs} target="_blank" rel="noreferrer" className="inline-flex w-fit items-center gap-1 text-xs text-primary">
          Get a key <ExternalLink className="size-3" />
        </a>
      )}
    </div>
  );
}

function RoleRow({ role, value, fallbacks, providers, owner, onChange }: {
  role: (typeof ROLES)[number];
  value: string | undefined;
  fallbacks: string[];
  providers: Provider[];
  owner: boolean;
  onChange: (v: string, fb?: string[]) => void;
}) {
  const usable = providers.filter((p) => p.roles.includes(role.id) && p.configured && p.enabled);
  const [prov, setProv] = useState(value?.split(":")[0] ?? usable[0]?.id ?? "");
  const [models, setModels] = useState<ModelOpt[]>([]);
  const [custom, setCustom] = useState(value?.split(":").slice(1).join(":") ?? "");
  useEffect(() => {
    if (!prov || prov === "local") return setModels(prov === "local" ? ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"].map((n) => ({ name: n, label: n })) : []);
    api<ModelOpt[]>(`/settings/providers/${prov}/models`).then(setModels).catch(() => setModels([]));
  }, [prov]);
  const current = value?.split(":").slice(1).join(":");
  return (
    <div className="grid gap-2 rounded-xl border p-4" data-testid={`role-${role.id}`}>
      <div>
        <p className="font-medium">{role.label}</p>
        <p className="text-xs text-muted-foreground">{role.hint}</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-[180px_1fr]">
        <Select value={prov} disabled={!owner} onValueChange={setProv} placeholder="Provider" options={usable.map((p) => ({ value: p.id, label: p.label.split(" (")[0] }))} />
        {models.length ? (
          <Select
            value={current && prov === value?.split(":")[0] ? current : undefined}
            disabled={!owner}
            placeholder="Choose a model"
            onValueChange={(m) => onChange(`${prov}:${m}`, fallbacks)}
            options={models.slice(0, 300).map((m) => ({ value: m.name, label: m.label, hint: m.label !== m.name ? m.name : undefined }))}
          />
        ) : (
          <div className="flex gap-2">
            <Input placeholder="Model name" value={custom} disabled={!owner} onChange={(e) => setCustom(e.target.value)} />
            <Button variant="outline" disabled={!owner || !custom || !prov} onClick={() => onChange(`${prov}:${custom}`, fallbacks)}>Use</Button>
          </div>
        )}
      </div>
      {role.fallback && (
        <div className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
          If it fails, try:
          {fallbacks.map((f) => (
            <Badge key={f} variant="secondary" className="gap-1">
              {f}
              {owner && (
                <button aria-label={`Remove fallback ${f}`} onClick={() => onChange(value ?? "", fallbacks.filter((x) => x !== f))}>
                  <X className="size-3" />
                </button>
              )}
            </Badge>
          ))}
          {owner && value && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                const ref = prompt("Fallback as provider:model (e.g. anthropic:claude-sonnet-4-5)");
                if (ref) onChange(value, [...fallbacks, ref.trim()]);
              }}
            >
              <Plus /> Add fallback
            </Button>
          )}
          {!fallbacks.length && !owner && <span>none</span>}
        </div>
      )}
    </div>
  );
}

export function ProvidersTab() {
  const me = useMe();
  const owner = me.role === "owner";
  const [providers, setProviders] = useState<Provider[]>([]);
  const [models, setModels] = useState<Record<string, string | string[]>>({});
  const load = useCallback(() => {
    api<Provider[]>("/settings/providers").then(setProviders).catch((e) => toast.error(e.message));
    api<{ models: Record<string, string | string[]> }>("/settings").then((s) => setModels(s.models ?? {})).catch(() => {});
  }, []);
  useEffect(load, [load]);

  const setRole = async (role: string, value: string, fb?: string[]) => {
    try {
      const body: Record<string, unknown> = { [role]: value };
      if (fb) body[`${role}_fallback`] = fb;
      const r = await api<{ models: Record<string, string | string[]> }>("/settings/roles", { method: "PUT", json: body });
      setModels(r.models);
      toast.success("Saved");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="grid max-w-4xl gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Which AI does what</CardTitle>
          <CardDescription>
            Pick a provider and model for each job. Fallbacks are tried in order when the first choice fails, so jobs keep working during an
            outage. {owner ? "" : "Only the owner can change these."}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {ROLES.map((r) => (
            <RoleRow
              key={r.id}
              role={r}
              value={models[r.id] as string | undefined}
              fallbacks={(models[`${r.id}_fallback`] as string[] | undefined) ?? []}
              providers={providers}
              owner={owner}
              onChange={(v, fb) => setRole(r.id, v, fb)}
            />
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Providers & keys</CardTitle>
            <CardDescription>Keys are encrypted on the server and never shown again. Each key is tested before it's saved.</CardDescription>
          </div>
          <Button size="icon" variant="ghost" onClick={load} aria-label="Refresh"><RefreshCw /></Button>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          {providers.map((p) => (
            <ProviderCard key={p.id} p={p} owner={owner} onSaved={load} />
          ))}
        </CardContent>
      </Card>
      <Field label="Tip" hint="Cheap + good defaults: OpenRouter or OpenAI gpt-4.1-mini for text, Flux (Replicate) for images, ElevenLabs or OpenAI for voice, Kling/Wan (Replicate) for AI video, Groq Whisper for fast transcription.">
        <span />
      </Field>
    </div>
  );
}
