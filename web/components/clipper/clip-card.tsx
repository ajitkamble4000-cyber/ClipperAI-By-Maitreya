"use client";

import { useEffect, useRef, useState } from "react";
import { Captions, Check, Copy, Download, Loader2, Minus, Palette, Plus, RotateCcw, Share2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { CaptionStylePicker } from "@/components/captions/caption-style-picker";
import { ClipTools } from "@/components/clipper/clip-tools";
import { ExtrasPanel, type Covers, type Ideas } from "@/components/clipper/extras-panel";
import { LockedBadge, useGate } from "@/components/plan/locked";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { api, downloadFrom, signedUrl } from "@/lib/api";
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
  mode: "ai" | "basic" | "whole";
  aspect?: Aspect;
  words_key?: string | null;
  language?: string | null;
  covers?: Covers | null;
  render_opts?: { music?: { mood?: string; volume?: number } } | null;
  ideas?: Ideas | null;
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

export type Aspect = "9:16" | "1:1" | "4:5" | "16:9";
export const ASPECT_CLASS: Record<Aspect, string> = {
  "9:16": "aspect-[9/16]",
  "1:1": "aspect-square",
  "4:5": "aspect-[4/5]",
  "16:9": "aspect-video",
};

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
  const gate = useGate();
  const aspect: Aspect = clip.aspect ?? "9:16";

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

  const captions = async (fmt: "srt" | "vtt" | "txt") => {
    try {
      await downloadFrom(`/clips/${clip.id}/captions.${fmt}`, `captions.${fmt}`);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const share = async () => {
    if (!gate.allowed("share_links")) return gate.explain("share_links");
    try {
      const r = await api<{ path: string }>(`/clips/${clip.id}/share`, { method: "POST", json: {} });
      const link = `${window.location.origin}${r.path}`;
      await navigator.clipboard.writeText(link).catch(() => {});
      toast.success("Share link copied", { description: link });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const reformat = (a: Aspect) => {
    if (a === aspect) return;
    if (a !== "9:16" && !gate.allowed("output_formats")) return gate.explain("output_formats");
    rerender({ aspect: a }, `Re-rendering as ${a}`);
  };

  const nudge = (which: "start" | "end", d: number) => {
    if (which === "start") setStart((v) => Math.max(0, Math.min(end - 3, +(v + d).toFixed(2))));
    else setEnd((v) => Math.max(start + 3, +(v + d).toFixed(2)));
  };

  return (
    <article
      className={cn("grid gap-4 rounded-xl border bg-card p-4", aspect === "16:9" ? "sm:grid-cols-[320px_1fr]" : "sm:grid-cols-[200px_1fr]")}
      data-testid="clip-card"
    >
      <div className={cn("relative mx-auto w-full sm:max-w-none", aspect === "16:9" ? "max-w-[420px]" : "max-w-[240px]")}>
        <div className={cn("relative overflow-hidden rounded-lg bg-black", ASPECT_CLASS[aspect])} data-testid="clip-frame" data-aspect={aspect}>
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
          {clip.mode === "whole" ? (
            <Badge variant="secondary" className="absolute left-2 top-2 bg-black/70 backdrop-blur" data-testid="whole-badge">
              <Captions className="size-3" /> Whole video
            </Badge>
          ) : (
            <Badge variant={scoreVariant(clip.virality_score)} className="absolute left-2 top-2 bg-black/70 backdrop-blur" data-testid="virality">
              <Sparkles className="size-3" /> {clip.virality_score}
            </Badge>
          )}
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
          <Button size="sm" variant="secondary" onClick={share} disabled={!clip.video_key || busy} aria-label="Share link" data-testid="share-clip">
            <Share2 />
          </Button>
        </div>
        {clip.words_key && !busy && (
          <div className="mt-2 flex items-center gap-1 text-xs" data-testid="caption-files">
            <span className="mr-1 text-muted-foreground">Captions{clip.language ? ` (${clip.language})` : ""}:</span>
            {(["srt", "vtt", "txt"] as const).map((f) => (
              <Button key={f} size="sm" variant="ghost" className="h-7 px-2 uppercase" onClick={() => captions(f)} aria-label={`Download ${f.toUpperCase()} captions`}>
                {f}
              </Button>
            ))}
          </div>
        )}
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
          <div className="mt-3 flex flex-wrap items-center gap-1" data-testid="format-row">
            <span className="mr-1 text-xs text-muted-foreground">Format</span>
            {(Object.keys(ASPECT_CLASS) as Aspect[]).map((a) => (
              <Button
                key={a}
                size="sm"
                variant={a === aspect ? "default" : "outline"}
                className="h-7 px-2 text-xs"
                disabled={busy || locked}
                onClick={() => reformat(a)}
                aria-pressed={a === aspect}
              >
                {a}
              </Button>
            ))}
            <LockedBadge feature="output_formats" className="ml-1" />
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
        <ClipTools
          clipId={clip.id}
          disabled={busy || locked || clip.status !== "ready"}
          music={clip.render_opts?.music}
          caption={[title, description, tags].filter(Boolean).join("\n\n")}
        />
        <ExtrasPanel
          base={`/clips/${clip.id}`}
          covers={clip.covers}
          ideas={clip.ideas}
          disabled={busy || locked || clip.status !== "ready"}
          onUseTitle={(t) => {
            setTitle(t);
            save({ title: t });
          }}
          onUseHashtags={(h) => {
            setTags(h.join(" "));
            save({ hashtags: h });
          }}
        />
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
