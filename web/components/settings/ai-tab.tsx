"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, KeyRound, RefreshCw, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";

export interface SettingsView {
  gemini_key_masked: string | null;
  gemini_key_source: "env" | "settings" | "none";
  models: Record<string, string>;
  monthly_budget_usd: number | null;
  proxy_set: boolean;
  cookies_set: boolean;
  source_retention_days: number;
  whisper_model: string;
  budget_state: { budget: number | null; spent: number; ratio: number; level: string };
}

type Roles = Record<"text" | "image" | "tts" | "video", { name: string; label: string }[]>;

const ROLE_LABELS: Record<keyof Roles, { label: string; hint: string }> = {
  text: { label: "Text model", hint: "Scripts, finding moments, rewrites" },
  image: { label: "Image model", hint: "Scene and character images (Gemini image models keep characters consistent)" },
  tts: { label: "Voice (TTS) model", hint: "Narration and voice previews" },
  video: { label: "Video model", hint: "Premium AI video (Veo)" },
};

const WHISPER = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"];

export function useSettings() {
  const [s, setS] = useState<SettingsView | null>(null);
  const load = useCallback(() => api<SettingsView>("/settings").then(setS).catch((e) => toast.error(e.message)), []);
  useEffect(() => {
    load();
  }, [load]);
  return { s, setS, load };
}

export function AiTab() {
  const { s, setS } = useSettings();
  const [key, setKey] = useState("");
  const [roles, setRoles] = useState<Roles | null>(null);
  const [testing, setTesting] = useState(false);
  const [budget, setBudget] = useState("");

  const loadModels = useCallback(() => {
    api<Roles>("/settings/models").then(setRoles).catch(() => setRoles(null));
  }, []);
  useEffect(() => {
    if (s && s.gemini_key_source !== "none") loadModels();
    if (s) setBudget(s.monthly_budget_usd?.toString() ?? "");
  }, [s?.gemini_key_source, s?.monthly_budget_usd]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!s) return null;

  const saveKey = async (value: string | null) => {
    try {
      setS(await api<SettingsView>("/settings/gemini-key", { method: "PUT", json: { key: value } }));
      setKey("");
      toast.success(value ? "Key saved and tested" : "Key removed");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const test = async () => {
    setTesting(true);
    type TestResult = { ok: boolean; error?: string; models?: number };
    const r: TestResult = await api<TestResult>("/settings/test-key", { method: "POST" }).catch((e: Error) => ({ ok: false, error: e.message }));
    setTesting(false);
    if (r.ok) toast.success(`Key works: ${r.models} models available`);
    else toast.error(r.error ?? "Key test failed");
  };

  const update = async (body: Record<string, unknown>, msg = "Saved") => {
    try {
      setS(await api<SettingsView>("/settings", { method: "PUT", json: body }));
      toast.success(msg);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const options = (role: keyof Roles) => {
    const list = roles?.[role] ?? [];
    const cur = s.models[role];
    const opts = list.map((m) => ({ value: m.name, label: m.label, hint: m.name }));
    if (cur && !list.some((m) => m.name === cur)) opts.unshift({ value: cur, label: cur, hint: "current (not in the list)" });
    return opts;
  };

  return (
    <div className="grid max-w-3xl gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="size-4" /> Gemini API key
          </CardTitle>
          <CardDescription>Stored encrypted and only used by the server. It is never sent back to browsers.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {s.gemini_key_source === "none" ? (
              <Badge variant="destructive">
                <XCircle className="size-3" /> Not set
              </Badge>
            ) : (
              <Badge variant="success">
                <CheckCircle2 className="size-3" /> {s.gemini_key_masked} {s.gemini_key_source === "env" && "(set via environment)"}
              </Badge>
            )}
            {s.gemini_key_source !== "none" && (
              <Button size="sm" variant="outline" onClick={test} disabled={testing} data-testid="test-key">
                {testing ? "Testing…" : "Test key"}
              </Button>
            )}
            {s.gemini_key_source === "settings" && (
              <Button size="sm" variant="ghost" onClick={() => confirm("Remove the Gemini key?") && saveKey(null)}>
                Remove
              </Button>
            )}
          </div>
          {s.gemini_key_source !== "env" && (
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input type="password" autoComplete="off" placeholder="Paste a key from Google AI Studio" value={key} onChange={(e) => setKey(e.target.value)} aria-label="Gemini API key" />
              <Button onClick={() => saveKey(key.trim())} disabled={key.trim().length < 20}>
                Save & test
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Models</CardTitle>
          <CardDescription>Choices come live from your key's models list, so new Gemini models show up automatically.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {(Object.keys(ROLE_LABELS) as (keyof Roles)[]).map((role) => (
            <Field key={role} label={ROLE_LABELS[role].label} hint={ROLE_LABELS[role].hint}>
              <Select
                value={s.models[role]}
                placeholder={roles ? "Choose a model" : "Add a key to load models"}
                disabled={!roles}
                onValueChange={(v) => update({ models: { ...s.models, [role]: v } }, "Model saved")}
                options={options(role)}
              />
            </Field>
          ))}
          <div className="sm:col-span-2">
            <Button size="sm" variant="ghost" onClick={loadModels} disabled={s.gemini_key_source === "none"}>
              <RefreshCw /> Refresh model list
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Monthly budget</CardTitle>
          <CardDescription>
            Everyone is warned at 80%. At 100% image, voice and video generation are paused (clipping falls back to basic mode) until next
            month or until you raise the budget.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <Field label="Budget (USD per month)" className="sm:w-56">
              <Input type="number" min={0} step={1} value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="No limit" aria-label="Monthly budget" />
            </Field>
            <Button onClick={() => (budget ? update({ monthly_budget_usd: Number(budget) }, "Budget saved") : update({ clear_budget: true }, "Budget removed"))}>
              Save budget
            </Button>
          </div>
          <p className="text-sm text-muted-foreground">
            This month: ${s.budget_state.spent.toFixed(2)}
            {s.budget_state.budget ? ` of $${s.budget_state.budget.toFixed(2)} (${Math.round(s.budget_state.ratio * 100)}%)` : " (no limit)"}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Transcription</CardTitle>
          <CardDescription>faster-whisper model size. Bigger is more accurate (especially for Hindi) but slower on CPU.</CardDescription>
        </CardHeader>
        <CardContent className="max-w-xs">
          <Select value={s.whisper_model} onValueChange={(v) => update({ whisper_model: v })} options={WHISPER.map((w) => ({ value: w, label: w }))} />
        </CardContent>
      </Card>
    </div>
  );
}
