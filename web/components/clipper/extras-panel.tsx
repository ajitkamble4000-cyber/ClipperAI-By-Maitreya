"use client";

import { useEffect, useState } from "react";
import { Download, ImageIcon, Lightbulb, Loader2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { LockedBadge, useGate } from "@/components/plan/locked";
import { Button } from "@/components/ui/button";
import { useJob } from "@/hooks/use-job";
import { api, signedUrl } from "@/lib/api";

export interface Covers {
  youtube?: string;
  vertical?: string;
  style?: "frame" | "ai";
}
export interface Ideas {
  titles?: string[];
  hashtags?: string[];
  description?: string;
}

/** AI thumbnails (YouTube 16:9 + vertical cover) and title/hashtag ideas for a clip or a story. */
export function ExtrasPanel({
  base,
  covers,
  ideas,
  disabled,
  onUseTitle,
  onUseHashtags,
}: {
  base: string; // "/clips/{id}" or "/story/{id}"
  covers: Covers | null | undefined;
  ideas: Ideas | null | undefined;
  disabled?: boolean;
  onUseTitle: (t: string) => void;
  onUseHashtags: (h: string[]) => void;
}) {
  const gate = useGate();
  const [jobId, setJobId] = useState<string | null>(null);
  const [kind, setKind] = useState<"thumb" | "ideas" | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const job = useJob(jobId);

  useEffect(() => {
    if (!job || !["succeeded", "failed", "canceled"].includes(job.status)) return;
    if (job.status === "failed") toast.error(job.error ?? "That didn't work. Your tokens were refunded.");
    if (job.status === "succeeded") toast.success(kind === "thumb" ? "Thumbnails ready" : "New ideas ready");
    setJobId(null);
    setKind(null);
  }, [job, kind]);

  useEffect(() => {
    if (!covers?.youtube) return setPreview(null);
    signedUrl(covers.youtube).then(setPreview).catch(() => {});
  }, [covers?.youtube]);

  const run = async (what: "thumb" | "ideas", style?: "frame" | "ai") => {
    const feature = what === "thumb" ? "thumbnails" : "title_variants";
    if (!gate.allowed(feature)) return gate.explain(feature);
    try {
      const r = await api<{ id: string }>(`${base}/${what === "thumb" ? "thumbnail" : "ideas"}`, {
        method: "POST",
        json: what === "thumb" ? { style } : undefined,
      });
      setKind(what);
      setJobId(r.id);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const download = async (key: string, name: string) => {
    window.location.href = await signedUrl(key, name);
  };
  const busy = !!jobId;

  return (
    <div className="grid gap-3 rounded-lg border p-3" data-testid="extras">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" disabled={busy || disabled} onClick={() => run("thumb", "frame")} data-testid="make-thumbnail">
          {kind === "thumb" ? <Loader2 className="animate-spin" /> : <ImageIcon />} Thumbnail
        </Button>
        <Button size="sm" variant="outline" disabled={busy || disabled} onClick={() => run("thumb", "ai")} title="AI-generated background">
          <Wand2 /> AI thumbnail
        </Button>
        <Button size="sm" variant="outline" disabled={busy || disabled} onClick={() => run("ideas")} data-testid="make-ideas">
          {kind === "ideas" ? <Loader2 className="animate-spin" /> : <Lightbulb />} Title ideas
        </Button>
        <LockedBadge feature="thumbnails" />
      </div>
      {preview && covers && (
        <div className="flex items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={preview} alt="Thumbnail" className="w-40 rounded border" data-testid="cover-preview" />
          <div className="grid gap-1 text-xs">
            {covers.youtube && (
              <button type="button" className="inline-flex items-center gap-1 text-primary hover:underline" onClick={() => download(covers.youtube!, "thumbnail-youtube.jpg")}>
                <Download className="size-3" /> YouTube 16:9
              </button>
            )}
            {covers.vertical && (
              <button type="button" className="inline-flex items-center gap-1 text-primary hover:underline" onClick={() => download(covers.vertical!, "cover-vertical.jpg")}>
                <Download className="size-3" /> Vertical cover
              </button>
            )}
          </div>
        </div>
      )}
      {ideas?.titles && ideas.titles.length > 0 && (
        <div className="grid gap-1.5" data-testid="ideas">
          <p className="text-xs text-muted-foreground">Click a title to use it</p>
          {ideas.titles.map((t) => (
            <button key={t} type="button" onClick={() => onUseTitle(t)} className="rounded-md border px-2 py-1 text-left text-sm hover:border-primary/60" data-testid="idea-title">
              {t}
            </button>
          ))}
          {ideas.hashtags && ideas.hashtags.length > 0 && (
            <button type="button" onClick={() => onUseHashtags(ideas.hashtags!)} className="text-left text-xs text-primary hover:underline">
              Use hashtags: {ideas.hashtags.join(" ")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
