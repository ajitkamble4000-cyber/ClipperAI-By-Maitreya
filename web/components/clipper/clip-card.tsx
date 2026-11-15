"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy, Download, Loader2, Minus, Palette, Plus, RotateCcw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { CaptionStylePicker } from "@/components/captions/caption-style-picker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { api, signedUrl } from "@/lib/api";
import { clipFilename, type CaptionStyle } from "@/lib/presets";
import { supabaseBrowser } from "@/lib/supabase/client";
import { cn, formatDuration } from "@/lib/utils";

export interface Clip {
  id: string;
  project_id: string;
  idx: number;
  start_s: number;
  end_s: number;
  title: string;
  hook_text: string;
  description: string;
  hashtags: string[];
  virality_score: number;
  reason: string;
  mode: "ai" | "basic";
  reframe: string;
  caption_style: CaptionStyle;
  status: string;
  video_key: string | null;
  thumb_key: string | null;
  duration_s: number | null;
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      type="button"
      size="icon"
      variant="ghost"
      aria-label={`Copy ${label}`}
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1200);
      }}
    >
      {done ? <Check className="text-success" /> : <Copy />}
    </Button>
  );
}

function scoreVariant(s: number) {
  return s >= 80 ? "success" : s >= 60 ? "warning" : "secondary";
}

export function ClipCard({ clip, locked }: { clip: Clip; locked?: boolean }) {
  const [src, setSrc] = useState<{ video: string; poster?: string } | null>(null);
  const [title, setTitle] = useState(clip.title);
  const [description, setDescription] = useState(clip.description);
  const [tags, setTags] = useState(clip.hashtags.join(" "));
  const [start, setStart] = useState(Number(clip.start_s));
  const [end, setEnd] = useState(Number(clip.end_s));
  const [styleOpen, setStyleOpen] = useState(false);
  const [style, setStyle] = useState<CaptionStyle>(clip.caption_style ?? { preset: "bold_pop" });
  const editing = useRef(false);

  useEffect(() => {
    if (!clip.video_key) return setSrc(null);
    let alive = true;
    Promise.all([signedUrl(clip.video_key), clip.thumb_key ? signedUrl(clip.thumb_key) : Promise.resolve(undefined)])
      .then(([video, poster]) => alive && setSrc({ video, poster }))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [clip.video_key, clip.thumb_key]);

  useEffect(() => {
    if (editing.current) return;
    setTitle(clip.title);
    setDescription(clip.description);
    setTags(clip.hashtags.join(" "));
    setStart(Number(clip.start_s));
    setEnd(Number(clip.end_s));
  }, [clip.title, clip.description, clip.hashtags, clip.start_s, clip.end_s]);

  const busy = ["pending", "queued", "rendering"].includes(clip.status);
  const nudged = Math.abs(start - Number(clip.start_s)) > 0.01 || Math.abs(end - Number(clip.end_s)) > 0.01;

  const save = async (patch: Partial<Clip>) => {
    editing.current = false;
    const { error } = await supabaseBrowser().from("clips").update(patch).eq("id", clip.id);
    if (error) toast.error(error.message);
  };

  const rerender = async (body: Record<string, unknown>, msg: string) => {
    try {
      await api(`/clips/${clip.id}/rerender`, { method: "POST", json: body });
      toast.success(msg);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const download = async () => {
    if (!clip.video_key) return;
    const url = await signedUrl(clip.video_key, clipFilename(clip.idx, title));
    window.location.href = url;
  };

  const nudge = (which: "start" | "end", d: number) => {
    if (which === "start") setStart((v) => Math.max(0, Math.min(end - 3, +(v + d).toFixed(2))));
    else setEnd((v) => Math.max(start + 3, +(v + d).toFixed(2)));
  };

  return (
    <article className="grid gap-4 rounded-xl border bg-card p-4 sm:grid-cols-[200px_1fr]" data-testid="clip-card">
      <div className="relative mx-auto w-full max-w-[240px] sm:max-w-none">
        <div className="relative aspect-[9/16] overflow-hidden rounded-lg bg-black">
          {src && !busy ? (
            <video key={src.video} src={src.video} poster={src.poster} controls playsInline preload="metadata" className="size-full object-cover" />
          ) : (
            <div className="flex size-full flex-col items-center justify-center gap-2 text-xs text-muted-foreground">
              {clip.status === "failed" ? (
                <span className="text-destructive">Render failed</span>
              ) : (
                <>
                  <Loader2 className="size-6 animate-spin text-primary" />
                  {clip.status === "pending" ? "Waiting…" : "Rendering…"}
                </>
              )}
            </div>
          )}
          <Badge variant={scoreVariant(clip.virality_score)} className="absolute left-2 top-2 bg-black/70 backdrop-blur" data-testid="virality">
            <Sparkles className="size-3" /> {clip.virality_score}
          </Badge>
          {clip.mode === "basic" && (
            <Badge variant="secondary" className="absolute right-2 top-2 bg-black/70">
              basic
            </Badge>
          )}
        </div>
        <div className="mt-2 flex gap-2">
          <Button size="sm" className="flex-1" onClick={download} disabled={!clip.video_key || busy}>
            <Download /> Download
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setStyleOpen(true)} disabled={busy || locked} aria-label="Change caption style">
            <Palette />
          </Button>
        </div>
      </div>

      <div className="grid min-w-0 content-start gap-3">
        <div>
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-muted-foreground" htmlFor={`t-${clip.id}`}>
              Title ({title.length}/60)
            </label>
            <CopyButton text={title} label="title" />
          </div>
          <Input
            id={`t-${clip.id}`}
            value={title}
            maxLength={100}
            onFocus={() => (editing.current = true)}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={() => title !== clip.title && save({ title })}
          />
        </div>
        <div>
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-muted-foreground" htmlFor={`d-${clip.id}`}>
              Description
            </label>
            <CopyButton text={description} label="description" />
          </div>
          <Textarea
            id={`d-${clip.id}`}
            rows={2}
            value={description}
            onFocus={() => (editing.current = true)}
            onChange={(e) => setDescription(e.target.value)}
            onBlur={() => description !== clip.description && save({ description })}
          />
        </div>
        <div>
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-muted-foreground" htmlFor={`h-${clip.id}`}>
              Hashtags
            </label>
            <CopyButton text={tags} label="hashtags" />
          </div>
          <Input
            id={`h-${clip.id}`}
            value={tags}
            onFocus={() => (editing.current = true)}
            onChange={(e) => setTags(e.target.value)}
            onBlur={() => {
              const list = tags.split(/[\s,]+/).filter(Boolean).map((t) => (t.startsWith("#") ? t : `#${t}`));
              if (list.join(" ") !== clip.hashtags.join(" ")) save({ hashtags: list });
            }}
          />
        </div>
        <div className="rounded-lg border p-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>
              Source {formatDuration(start)} → {formatDuration(end)} · {(end - start).toFixed(1)} s
            </span>
            {clip.reason && <span className="line-clamp-1 italic">{clip.reason}</span>}
          </div>
          <div className="mt-2 grid gap-2">
            {(["start", "end"] as const).map((w) => (
              <div key={w} className="flex items-center gap-1">
                <span className="w-9 text-xs capitalize text-muted-foreground">{w}</span>
                <Button size="sm" variant="outline" onClick={() => nudge(w, -1)} aria-label={`${w} minus 1 second`} disabled={busy || locked}>
                  <Minus />
                </Button>
                <span className="w-12 text-center text-sm tabular-nums">{(w === "start" ? start : end).toFixed(1)}</span>
                <Button size="sm" variant="outline" onClick={() => nudge(w, 1)} aria-label={`${w} plus 1 second`} disabled={busy || locked}>
                  <Plus />
                </Button>
              </div>
            ))}
          </div>
          {nudged && (
            <div className="mt-3 flex gap-2">
              <Button size="sm" onClick={() => rerender({ start, end }, "Re-rendering with the new timing")}>
                <RotateCcw /> Apply & re-render
              </Button>
              <Button size="sm" variant="ghost" onClick={() => { setStart(Number(clip.start_s)); setEnd(Number(clip.end_s)); }}>
                Reset
              </Button>
            </div>
          )}
        </div>
      </div>

      <Dialog open={styleOpen} onOpenChange={setStyleOpen}>
        <DialogContent className="max-w-3xl">
          <DialogTitle>Change caption style</DialogTitle>
          <DialogDescription>Only the captions are re-rendered; the cut and framing stay the same.</DialogDescription>
          <CaptionStylePicker value={style} onChange={setStyle} hook={clip.hook_text} compact />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setStyleOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                setStyleOpen(false);
                rerender({ caption_style: style }, "Re-rendering captions");
              }}
              data-testid="apply-style"
            >
              Apply
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <span className={cn("sr-only")} data-testid="clip-status">
        {clip.status}
      </span>
    </article>
  );
}
