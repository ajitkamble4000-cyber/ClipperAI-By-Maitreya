"use client";

import { useCallback, useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

interface Price {
  model: string;
  input_per_mtok: number;
  output_per_mtok: number;
  audio_out_per_mtok: number;
  per_image: number;
  per_video_second: number;
}

const COLS: { key: keyof Price; label: string }[] = [
  { key: "input_per_mtok", label: "Input /1M tok" },
  { key: "output_per_mtok", label: "Output /1M tok" },
  { key: "audio_out_per_mtok", label: "Audio out /1M tok" },
  { key: "per_image", label: "Per image" },
  { key: "per_video_second", label: "Per video s" },
];

export function PricingTab() {
  const [rows, setRows] = useState<Price[]>([]);
  const [draft, setDraft] = useState("");
  const load = useCallback(() => {
    api<Price[]>("/settings/pricing").then(setRows).catch((e) => toast.error(e.message));
  }, []);
  useEffect(load, [load]);

  const save = async (p: Price) => {
    try {
      await api("/settings/pricing", { method: "PUT", json: p });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <Card className="max-w-5xl">
      <CardHeader>
        <CardTitle>Pricing (USD)</CardTitle>
        <CardDescription>
          The Gemini API doesn't report prices, so cost estimates use this table. Rows match by model-name prefix (longest wins). Check
          Google's current price list and adjust.
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="py-2 pr-2 font-medium">Model prefix</th>
              {COLS.map((c) => (
                <th key={c.key} className="px-1 py-2 font-medium">
                  {c.label}
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.model} className="border-t">
                <td className="py-1.5 pr-2 font-mono text-xs">{r.model}</td>
                {COLS.map((c) => (
                  <td key={c.key} className="px-1 py-1">
                    <Input
                      type="number"
                      step="0.001"
                      min={0}
                      className="h-8 w-24"
                      value={Number(r[c.key])}
                      onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, [c.key]: Number(e.target.value) } : x)))}
                      onBlur={() => save(rows[i])}
                      aria-label={`${r.model} ${c.label}`}
                    />
                  </td>
                ))}
                <td>
                  <Button size="icon" variant="ghost" aria-label={`Delete ${r.model}`} onClick={() => api(`/settings/pricing/${encodeURIComponent(r.model)}`, { method: "DELETE" }).then(load)}>
                    <Trash2 />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-3 flex gap-2">
          <Input className="max-w-xs" placeholder="New model prefix, e.g. gemini-3-flash" value={draft} onChange={(e) => setDraft(e.target.value)} />
          <Button
            variant="outline"
            disabled={draft.length < 2}
            onClick={() =>
              save({ model: draft, input_per_mtok: 0, output_per_mtok: 0, audio_out_per_mtok: 0, per_image: 0, per_video_second: 0 }).then(() => {
                setDraft("");
                load();
              })
            }
          >
            Add row
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
