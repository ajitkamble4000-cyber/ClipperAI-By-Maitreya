"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Loader2, Trash2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useAutosave } from "@/hooks/use-autosave";
import { api } from "@/lib/api";
import { CAMERA_MOTIONS, estimateSeconds } from "@/lib/story";

export interface Scene {
  id: string;
  project_id: string;
  idx: number;
  narration: string;
  image_prompt: string;
  camera_motion: string;
  duration_estimate: number;
  sfx_suggestion: string;
  on_screen_text: string;
  image_key: string | null;
  image_source: string | null;
  video_key: string | null;
  video_status: string | null;
  use_premium: boolean;
  audio_start_s: number | null;
  audio_end_s: number | null;
}

const FIELDS = ["narration", "image_prompt", "camera_motion", "sfx_suggestion", "on_screen_text"] as const;
type F = (typeof FIELDS)[number];

export function SceneCard({
  scene,
  position,
  total,
  onMove,
  onDelete,
  aiBusy,
  children,
}: {
  scene: Scene;
  position: number;
  total: number;
  onMove: (dir: -1 | 1) => void;
  onDelete: () => void;
  aiBusy: boolean;
  children?: React.ReactNode;
}) {
  const { save } = useAutosave("scenes", { id: scene.id });
  const [v, setV] = useState<Record<F, string>>(() => Object.fromEntries(FIELDS.map((f) => [f, String(scene[f] ?? "")])) as Record<F, string>);
  const focused = useRef<F | null>(null);
  const [instruction, setInstruction] = useState("");
  const [rewriting, setRewriting] = useState(false);

  // Take teammates' / AI edits, except for the field this user is typing in.
  useEffect(() => {
    setV((prev) => {
      const next = { ...prev };
      for (const f of FIELDS) if (focused.current !== f) next[f] = String(scene[f] ?? "");
      return next;
    });
    setRewriting(false);
  }, [scene.narration, scene.image_prompt, scene.camera_motion, scene.sfx_suggestion, scene.on_screen_text]); // eslint-disable-line react-hooks/exhaustive-deps

  const change = (f: F, value: string) => {
    setV((p) => ({ ...p, [f]: value }));
    const patch: Record<string, unknown> = { [f]: value };
    if (f === "narration") patch.duration_estimate = Math.max(1.5, +estimateSeconds(value).toFixed(1));
    save(patch);
  };

  const rewrite = async () => {
    setRewriting(true);
    try {
      await api(`/scenes/${scene.id}/rewrite`, { method: "POST", json: { instruction: instruction || null } });
      setInstruction("");
    } catch (e) {
      toast.error((e as Error).message);
      setRewriting(false);
    }
  };

  const secs = estimateSeconds(v.narration);
  const field = (f: F) => ({
    value: v[f],
    onFocus: () => (focused.current = f),
    onBlur: () => (focused.current = null),
  });

  return (
    <article className="rounded-xl border bg-card p-4" data-testid="scene-card">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex size-7 items-center justify-center rounded-full bg-primary/15 text-sm font-semibold text-primary">{position + 1}</span>
          <span className="text-xs text-muted-foreground">~{secs.toFixed(1)} s</span>
        </div>
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" disabled={position === 0} onClick={() => onMove(-1)} aria-label="Move scene up">
            <ArrowUp />
          </Button>
          <Button size="icon" variant="ghost" disabled={position === total - 1} onClick={() => onMove(1)} aria-label="Move scene down">
            <ArrowDown />
          </Button>
          <Button size="icon" variant="ghost" onClick={onDelete} aria-label="Delete scene">
            <Trash2 />
          </Button>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_1fr_auto]">
        <div className="grid gap-1.5">
          <label className="text-xs font-medium text-muted-foreground" htmlFor={`n-${scene.id}`}>
            Narration
          </label>
          <Textarea id={`n-${scene.id}`} rows={4} {...field("narration")} onChange={(e) => change("narration", e.target.value)} />
        </div>
        <div className="grid gap-1.5">
          <label className="text-xs font-medium text-muted-foreground" htmlFor={`p-${scene.id}`}>
            Image prompt
          </label>
          <Textarea id={`p-${scene.id}`} rows={4} {...field("image_prompt")} onChange={(e) => change("image_prompt", e.target.value)} />
        </div>
        {children}
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <Select value={v.camera_motion} onValueChange={(m) => change("camera_motion", m)} options={CAMERA_MOTIONS.map((m) => ({ value: m, label: `Camera: ${m}` }))} />
        <Input placeholder="Sound effect (e.g. whoosh)" {...field("sfx_suggestion")} onChange={(e) => change("sfx_suggestion", e.target.value)} aria-label="Sound effect" />
        <Input placeholder="On-screen text (optional)" {...field("on_screen_text")} onChange={(e) => change("on_screen_text", e.target.value)} aria-label="On-screen text" />
      </div>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <Input placeholder="Optional: how to rewrite (e.g. make it scarier)" value={instruction} onChange={(e) => setInstruction(e.target.value)} aria-label="Rewrite instruction" />
        <Button variant="secondary" onClick={rewrite} disabled={aiBusy || rewriting} className="shrink-0">
          {rewriting ? <Loader2 className="animate-spin" /> : <Wand2 />} Rewrite this scene
        </Button>
      </div>
    </article>
  );
}
