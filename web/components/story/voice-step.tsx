"use client";

import { useRef, useState } from "react";
import { Mic, Play, X } from "lucide-react";
import { toast } from "sonner";
import { UploadDropzone } from "@/components/upload/upload-dropzone";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Select } from "@/components/ui/select";
import { useAutosave } from "@/hooks/use-autosave";
import { api } from "@/lib/api";
import { GENRES, SPEAKING_STYLES, VOICES } from "@/lib/story";
import { isActive, latestJob, StepJob, useSigned } from "./step-utils";
import type { StepProps } from "./steps-registry";

export function VoiceStep({ story, scenes, jobs }: StepProps) {
  const pid = story.project_id;
  const { save } = useAutosave("stories", { project_id: pid }, 200);
  const [voice, setVoice] = useState(story.voice ?? GENRES[story.genre]?.voice ?? "Charon");
  const [style, setStyle] = useState(story.speaking_style);
  const job = latestJob(jobs, ["story_voice"]);
  const narration = useSigned(story.narration_key);
  const audio = useRef<HTMLAudioElement | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const timed = scenes.filter((s) => s.audio_start_s !== null).length === scenes.length;

  const preview = async () => {
    setPreviewing(true);
    try {
      const { url } = await api<{ url: string }>(`/story/voices/preview?voice=${voice}&style=${style}`);
      audio.current?.pause();
      audio.current = new Audio(url);
      await audio.current.play();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setPreviewing(false);
    }
  };

  const generate = async () => {
    try {
      await api(`/story/${pid}/voice`, { method: "POST" });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Voiceover</CardTitle>
        <CardDescription>
          The whole narration is voiced in one take for a consistent delivery. Every word is then timed, which sets each scene's exact
          length and drives the captions.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        {!story.voiceover_key ? (
          <div className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <Field label="Voice">
              <Select value={voice} onValueChange={(v) => { setVoice(v); save({ voice: v }); }} options={VOICES.map((v) => ({ value: v.name, label: `${v.name} · ${v.desc}` }))} />
            </Field>
            <Field label="Speaking style">
              <Select value={style} onValueChange={(v) => { setStyle(v); save({ speaking_style: v }); }} options={Object.entries(SPEAKING_STYLES).map(([v, s]) => ({ value: v, label: s.label }))} />
            </Field>
            <Button variant="outline" onClick={preview} disabled={previewing}>
              <Play /> {previewing ? "Loading…" : "Preview"}
            </Button>
          </div>
        ) : (
          <div className="flex items-center justify-between rounded-lg border p-3 text-sm">
            <span className="flex items-center gap-2"><Mic className="size-4 text-primary" /> Using your uploaded voiceover</span>
            <Button size="sm" variant="ghost" onClick={() => api(`/story/${pid}/voiceover`, { method: "PUT", json: { upload_id: null } })}>
              <X /> Use AI voice instead
            </Button>
          </div>
        )}
        <details className="rounded-lg border p-3">
          <summary className="cursor-pointer text-sm font-medium">Or upload my own recording</summary>
          <p className="mt-2 text-xs text-muted-foreground">Read the narration as written; it will be timed against the script.</p>
          <UploadDropzone
            purpose="voiceover"
            className="mt-3"
            onComplete={(u) => api(`/story/${pid}/voiceover`, { method: "PUT", json: { upload_id: u.id } }).then(() => toast.success("Voiceover saved. Now time it."))}
          />
        </details>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={generate} disabled={isActive(job)} data-testid="generate-voice">
            {story.voiceover_key ? "Time my recording" : story.narration_key ? "Regenerate voiceover" : "Generate voiceover"}
          </Button>
          {narration && <audio controls src={narration} className="h-10 max-w-full" />}
        </div>
        <StepJob job={job} />
        {timed && story.narration_key && (
          <div className="grid gap-1 text-xs text-muted-foreground" data-testid="scene-timings">
            {[...scenes].sort((a, b) => a.idx - b.idx).map((s) => (
              <div key={s.id} className="flex gap-2">
                <span className="w-16 tabular-nums">{Number(s.audio_start_s).toFixed(1)}–{Number(s.audio_end_s).toFixed(1)}s</span>
                <span className="truncate">{s.narration}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
