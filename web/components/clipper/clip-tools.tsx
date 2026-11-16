"use client";

import { useEffect, useState } from "react";
import { FileAudio, ImagePlay, Music, PencilLine } from "lucide-react";
import { toast } from "sonner";
import { ScheduleButton } from "@/components/calendar/schedule-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useJob } from "@/hooks/use-job";
import { api, signedUrl } from "@/lib/api";

export const MUSIC_MOODS = [
  { value: "none", label: "No music" },
  { value: "auto", label: "Auto (fits the video)" },
  { value: "calm", label: "Calm" },
  { value: "upbeat", label: "Upbeat" },
  { value: "epic", label: "Epic" },
  { value: "emotional", label: "Emotional" },
  { value: "funny", label: "Funny" },
  { value: "suspense", label: "Suspense" },
  { value: "horror", label: "Horror" },
];

interface Cue {
  start: number;
  end: number;
  text: string;
}

const fmt = (t: number) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`;

/** Fix caption words, export MP3/GIF, set background music: the editing tools on a finished clip. */
export function ClipTools({
  clipId,
  disabled,
  music,
  caption,
}: {
  clipId: string;
  disabled?: boolean;
  music?: { mood?: string; volume?: number };
  caption?: string;
}) {
  const [open, setOpen] = useState(false);
  const [cues, setCues] = useState<Cue[] | null>(null);
  const [exportJob, setExportJob] = useState<string | null>(null);
  const [mood, setMood] = useState(music?.mood ?? "none");
  const job = useJob(exportJob);

  useEffect(() => {
    if (!job) return;
    if (job.status === "succeeded" && job.result?.key) {
      signedUrl(String(job.result.key), String(job.result.filename ?? "export")).then((u) => (window.location.href = u));
      setExportJob(null);
    } else if (job.status === "failed") {
      toast.error(job.error ?? "Export failed");
      setExportJob(null);
    }
  }, [job]);

  const openEditor = async () => {
    setOpen(true);
    setCues(null);
    try {
      setCues(await api<Cue[]>(`/clips/${clipId}/cues`));
    } catch (e) {
      toast.error((e as Error).message);
      setOpen(false);
    }
  };
  const saveCues = async () => {
    try {
      await api(`/clips/${clipId}/captions`, { method: "POST", json: { cues } });
      toast.success("Captions saved. Re-rendering…");
      setOpen(false);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const exportAs = async (format: "mp3" | "gif") => {
    try {
      const r = await api<{ id: string }>(`/clips/${clipId}/export`, { method: "POST", json: { format } });
      setExportJob(r.id);
      toast.message(`Preparing ${format.toUpperCase()}…`);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const setMusic = async (m: string) => {
    setMood(m);
    try {
      await api(`/clips/${clipId}/rerender`, { method: "POST", json: { music_mood: m } });
      toast.success(m === "none" ? "Removing music…" : "Adding music…");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="clip-tools">
      <Button size="sm" variant="outline" onClick={openEditor} disabled={disabled} data-testid="edit-captions">
        <PencilLine /> Edit captions
      </Button>
      <Button size="sm" variant="outline" onClick={() => exportAs("mp3")} disabled={disabled || !!exportJob} data-testid="export-mp3">
        <FileAudio /> MP3
      </Button>
      <Button size="sm" variant="outline" onClick={() => exportAs("gif")} disabled={disabled || !!exportJob} data-testid="export-gif">
        <ImagePlay /> GIF
      </Button>
      <ScheduleButton clipId={clipId} defaultCaption={caption} />
      <span className="inline-flex items-center gap-1">
        <Music className="size-4 text-muted-foreground" />
        <Select value={mood} onValueChange={setMusic} disabled={disabled} className="h-8 w-44 text-xs" aria-label="Background music" options={MUSIC_MOODS} />
      </span>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogTitle>Edit captions</DialogTitle>
          <DialogDescription>Fix any word, then save. Only the captions are re-rendered; the timing and cut stay the same.</DialogDescription>
          <div className="grid max-h-[60vh] gap-2 overflow-y-auto pr-1" data-testid="cue-list">
            {cues === null ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : (
              cues.map((c, i) => (
                <div key={`${c.start}-${i}`} className="flex items-center gap-2">
                  <span className="w-24 shrink-0 text-xs tabular-nums text-muted-foreground">
                    {fmt(c.start)}–{fmt(c.end)}
                  </span>
                  <Input
                    value={c.text}
                    maxLength={200}
                    aria-label={`Caption line ${i + 1}`}
                    onChange={(e) => setCues((list) => list!.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))}
                  />
                </div>
              ))
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={saveCues} disabled={!cues} data-testid="save-captions">
              Save & re-render
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
