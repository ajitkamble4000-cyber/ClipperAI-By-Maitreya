"use client";

import { useEffect, useState } from "react";
import { ImageIcon, Loader2, RefreshCw, Upload, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { UploadDropzone } from "@/components/upload/upload-dropzone";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { Job } from "@/hooks/use-job";
import { api } from "@/lib/api";
import type { Scene } from "./scene-card";
import { isActive, latestJob, StepJob, useSigned } from "./step-utils";
import type { StepProps } from "./steps-registry";

interface Estimate {
  model: string;
  images: number;
  characters: number;
  per_image: number;
  estimated_usd: number;
  budget: { level: string; spent: number; budget: number | null };
}

function SceneImage({ scene, job }: { scene: Scene; job?: Job }) {
  const url = useSigned(scene.image_key);
  const [edit, setEdit] = useState("");
  const [upload, setUpload] = useState(false);
  const busy = isActive(job);
  const go = async (instruction?: string) => {
    try {
      await api(`/scenes/${scene.id}/image`, { method: "POST", json: { instruction: instruction || null } });
      setEdit("");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  return (
    <div className="grid gap-2" data-testid="scene-image">
      <div className="relative aspect-[9/16] overflow-hidden rounded-lg border bg-muted">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {url ? <img src={url} alt={`Scene ${scene.idx + 1}`} className="size-full object-cover" /> : <ImageIcon className="absolute left-1/2 top-1/2 size-6 -translate-x-1/2 -translate-y-1/2 text-muted-foreground" />}
        {busy && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/60">
            <Loader2 className="size-6 animate-spin text-primary" />
          </div>
        )}
        <span className="absolute left-1.5 top-1.5 rounded bg-black/70 px-1.5 text-xs">{scene.idx + 1}</span>
        {scene.image_source === "upload" && <span className="absolute right-1.5 top-1.5 rounded bg-black/70 px-1.5 text-[10px]">yours</span>}
      </div>
      <p className="line-clamp-2 text-xs text-muted-foreground" title={scene.image_prompt}>{scene.image_prompt}</p>
      <div className="flex gap-1">
        <Button size="sm" variant="secondary" className="flex-1" disabled={busy} onClick={() => go()} aria-label={`Regenerate image ${scene.idx + 1}`}>
          <RefreshCw /> {scene.image_key ? "Redo" : "Make"}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setUpload(true)} aria-label={`Upload image ${scene.idx + 1}`}>
          <Upload />
        </Button>
      </div>
      {scene.image_key && (
        <div className="flex gap-1">
          <Input className="h-8 text-xs" placeholder="Edit: make it night time" value={edit} onChange={(e) => setEdit(e.target.value)} />
          <Button size="sm" variant="ghost" disabled={busy || !edit.trim()} onClick={() => go(edit)} aria-label="Apply edit">
            <Wand2 />
          </Button>
        </div>
      )}
      <Dialog open={upload} onOpenChange={setUpload}>
        <DialogContent>
          <DialogTitle>Use your own image for scene {scene.idx + 1}</DialogTitle>
          <UploadDropzone
            purpose="image"
            onComplete={async (u) => {
              await api(`/scenes/${scene.id}/image/upload`, { method: "POST", json: { upload_id: u.id } }).catch((e) => toast.error(e.message));
              setUpload(false);
            }}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function ImagesStep({ story, scenes, jobs }: StepProps) {
  const pid = story.project_id;
  const all = latestJob(jobs, ["story_images"]);
  const [est, setEst] = useState<Estimate | null>(null);
  const missing = scenes.filter((s) => !s.image_key).length;
  useEffect(() => {
    api<Estimate>(`/story/${pid}/estimate?what=images`).then(setEst).catch(() => {});
  }, [pid, missing]);

  const generate = async () => {
    try {
      await api(`/story/${pid}/images`, { method: "POST", json: { only_missing: true } });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const sorted = [...scenes].sort((a, b) => a.idx - b.idx);
  const sceneJob = (s: Scene) =>
    latestJob(jobs, ["story_image_one"], (j) => j.params?.scene_id === s.id && isActive(j)) ?? (isActive(all) && !s.image_key ? all : undefined);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Scene images</CardTitle>
        <CardDescription>
          9:16 images in the story's style, generated in parallel. Redo, edit with a prompt, or upload your own for any scene.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 text-sm">
          <span>
            {missing} of {scenes.length} scenes need an image
            {est && est.model && missing > 0 && (
              <span className="text-muted-foreground">
                {" "}· est. ${est.estimated_usd.toFixed(2)} with {est.model}
                {est.characters > 0 && ` (incl. ${est.characters} character reference${est.characters > 1 ? "s" : ""})`}
              </span>
            )}
            {est?.budget.level === "warn" && <span className="text-warning"> · 80% of this month's budget used</span>}
            {est?.budget.level === "blocked" && <span className="text-destructive"> · monthly budget reached</span>}
          </span>
          <Button onClick={generate} disabled={!missing || isActive(all) || est?.budget.level === "blocked"} data-testid="generate-images">
            Generate {missing} image{missing === 1 ? "" : "s"}
          </Button>
        </div>
        <StepJob job={all} />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {sorted.map((s) => (
            <SceneImage key={s.id} scene={s} job={sceneJob(s)} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
