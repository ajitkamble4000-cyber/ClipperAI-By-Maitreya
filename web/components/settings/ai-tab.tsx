"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

export interface SettingsView {
  gemini_key_masked: string | null;
  gemini_key_source: "env" | "settings" | "none";
  models: Record<string, string | string[]>;
  monthly_budget_usd: number | null;
  proxy_set: boolean;
  cookies_set: boolean;
  source_retention_days: number;
  whisper_model: string;
  budget_state: { budget: number | null; spent: number; ratio: number; level: string };
}

export function useSettings() {
  const [s, setS] = useState<SettingsView | null>(null);
  const load = useCallback(() => api<SettingsView>("/settings").then(setS).catch((e) => toast.error(e.message)), []);
  useEffect(() => {
    load();
  }, [load]);
  return { s, setS, load };
}

/** Monthly AI spend limit (provider costs). Tokens are what users pay; this protects the business's bill. */
export function AiTab() {
  const { s, setS } = useSettings();
  const [budget, setBudget] = useState("");
  useEffect(() => {
    if (s) setBudget(s.monthly_budget_usd?.toString() ?? "");
  }, [s?.monthly_budget_usd]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!s) return null;

  const update = async (body: Record<string, unknown>, msg = "Saved") => {
    try {
      setS(await api<SettingsView>("/settings", { method: "PUT", json: body }));
      toast.success(msg);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="grid max-w-3xl gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Monthly AI budget</CardTitle>
          <CardDescription>
            A safety cap on what AI providers can cost you each month. Everyone is warned at 80%; at 100% image, voice and video
            generation pause (clipping falls back to basic mode) until next month or until you raise it.
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
    </div>
  );
}
