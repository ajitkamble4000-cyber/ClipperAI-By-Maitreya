"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Film, Loader2, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { supabaseBrowser } from "@/lib/supabase/client";
import type { Scene } from "./scene-card";
import { isActive, latestJob, StepJob, useSigned } from "./step-utils";
import type { StepProps } from "./steps-registry";

interface VeoEstimate {
  model: string;
  scenes: number;
  seconds: number;
  per_second: number;
  estimated_usd: number;
  budget: { level: string; spent: number; budget: number | null };
}

type SceneVeo = Scene & { veo_error?: string | null };

const usd = (n: number) => `$${n.toFixed(2)}`;

function SceneRow({
  s,
  checked,
  onToggle,
  onRetry,
}: {
  s: SceneVeo;
  checked: boolean;
  onToggle: (v: boolean) => void;
  onRetry: () => void;
}) {
  const clip = useSigned(s.video_status === "done" ? s.video_key : null);
  const thumb = useSigned(s.image_key);
  return (
    <div className="flex items-center gap-3 rounded-lg border p-2" data-testid="veo-scene">
      <input
        type="checkbox"
        className="size-4 accent-[var(--primary)]"
        checked={checked}
        onChange={(e) => onToggle(e.target.checked)}
        aria-label={`Use AI video for scene ${s.idx + 1}`}
      />
      <div className="aspect-[9/16] w-12 shrink-0 overflow-hidden rounded bg-muted">
        {clip ? (
          <video src={clip} muted loop autoPlay playsInline className="size-full object-cover" />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          thumb && <img src={thumb} alt="" className="size-full object-cover" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm">Scene {s.idx + 1}</p>
        <p className="truncate text-xs text-muted-foreground">{s.narration}</p>
        {s.video_status === "failed" && s.veo_error && <p className="truncate text-xs text-destructive">{s.veo_error}</p>}
      </div>
      {s.video_status === "done" && (
        <Badge variant="success">
          <CheckCircle2 className="size-3" /> video
        </Badge>
      )}
      {(s.video_status === "running" || s.video_status === "queued") && (
        <Badge variant="warning">
          <Loader2 className="size-3 animate-spin" /> {s.video_status}
        </Badge>
      )}
      {s.video_status === "failed" && (
        <Button size="sm" variant="secondary" onClick={onRetry} aria-label={`Retry scene ${s.idx + 1}`}>
          <RotateCcw /> Retry
        </Button>
      )}
    </div>
  );
}

export function PremiumPanel({ story, scenes, jobs }: StepProps) {
  const pid = story.project_id;
  const sorted = useMemo(() => [...(scenes as SceneVeo[])].sort((a, b) => a.idx - b.idx), [scenes]);
  // Optimistic selection: the click shows immediately; the database write and Realtime echo follow.
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const premiumKey = sorted.map((s) => `${s.id}:${s.use_premium}`).join(",");
  useEffect(() => {
    setSelected(Object.fromEntries(sorted.map((s) => [s.id, s.use_premium])));
  }, [premiumKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const isChosen = (s: Scene) => selected[s.id] ?? s.use_premium;
  const chosen = sorted.filter((s) => isChosen(s) && s.video_status !== "done");
  const chosenKey = chosen.map((s) => s.id).join(",");
  const job = latestJob(jobs, ["story_veo"]);
  const [est, setEst] = useState<VeoEstimate | null>(null);
  const [confirm, setConfirm] = useState<{ ids: string[]; est: VeoEstimate } | null>(null);

  useEffect(() => {
    if (!chosenKey) return setEst(null);
    api<VeoEstimate>(`/story/${pid}/estimate?what=veo&scene_ids=${chosenKey}`).then(setEst).catch(() => {});
  }, [pid, chosenKey]);

  const toggle = (s: Scene, v: boolean) => {
    setSelected((p) => ({ ...p, [s.id]: v }));
    return supabaseBrowser()
      .from("scenes")
      .update({ use_premium: v })
      .eq("id", s.id)
      .then(({ error }) => error && toast.error(error.message));
  };

  const ask = async (ids: string[]) => {
    try {
      const e = await api<VeoEstimate>(`/story/${pid}/estimate?what=veo&scene_ids=${ids.join(",")}`);
      setConfirm({ ids, est: e });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const go = async () => {
    if (!confirm) return;
    try {
      await api(`/story/${pid}/veo`, { method: "POST", json: { scene_ids: confirm.ids, confirm_usd: confirm.est.estimated_usd } });
      toast.success("AI video started. Scenes update as each clip finishes.");
    } catch (e) {
      toast.error((e as Error).message);
    }
    setConfirm(null);
  };

  return (
    <div className="grid gap-3">
      <p className="text-sm text-muted-foreground">
        Pick the scenes to turn into AI video (Veo). Unchecked scenes use standard motion. Clips are a few seconds long; longer scenes are
        gently slowed or held on the last frame.
      </p>
      <div className="grid gap-2">
        {sorted.map((s) => (
          <SceneRow key={s.id} s={s} checked={isChosen(s)} onToggle={(v) => toggle(s, v)} onRetry={() => ask([s.id])} />
        ))}
      </div>
      <StepJob job={job} />
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm">
        <span>
          {chosen.length} scene{chosen.length === 1 ? "" : "s"} selected
          {est && ` · ${est.seconds} s of video · est. ${usd(est.estimated_usd)}`}
        </span>
        <Button onClick={() => ask(chosen.map((s) => s.id))} disabled={!chosen.length || isActive(job)} data-testid="veo-generate">
          <Film /> Generate AI video
        </Button>
      </div>
      <Dialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent>
          <DialogTitle>Confirm AI video cost</DialogTitle>
          {confirm && (
            <>
              <DialogDescription>
                {confirm.est.scenes} scene{confirm.est.scenes === 1 ? "" : "s"} · {confirm.est.seconds} seconds with {confirm.est.model} at ~
                {usd(confirm.est.per_second)}/s.
              </DialogDescription>
              <p className="text-3xl font-semibold" data-testid="veo-cost">
                {usd(confirm.est.estimated_usd)}
              </p>
              {confirm.est.budget.budget ? (
                <p className="text-sm text-muted-foreground">
                  This month: {usd(confirm.est.budget.spent)} of {usd(confirm.est.budget.budget)} used.
                </p>
              ) : null}
              {confirm.est.budget.level !== "ok" && (
                <p className="flex items-center gap-2 text-sm text-warning">
                  <AlertTriangle className="size-4" />
                  {confirm.est.budget.level === "blocked" ? "Monthly budget reached." : "Over 80% of the monthly budget is used."}
                </p>
              )}
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setConfirm(null)}>
                  Cancel
                </Button>
                <Button onClick={go} disabled={confirm.est.budget.level === "blocked"} data-testid="veo-confirm">
                  Generate for {usd(confirm.est.estimated_usd)}
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
