"use client";

import { useEffect, useState } from "react";
import { Clock, Globe, Info } from "lucide-react";
import { api } from "@/lib/api";

export interface LinkInfo {
  url: string;
  platform: string;
  label: string;
  short_form: boolean;
  help: string | null;
  title?: string | null;
  duration?: number | null;
  thumbnail?: string | null;
  uploader?: string | null;
  error?: string;
  suggested_mode?: "captions" | "clips";
  too_long?: boolean;
}

export const isUrl = (s: string) => /^https?:\/\/\S+\.\S+/.test(s.trim());

export function fmtDuration(s: number) {
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}:${String(sec).padStart(2, "0")}`;
}

/** Looks a pasted link up (platform always; title/length when the site allows) after a short pause in typing. */
export function useLinkInfo(url: string) {
  const [info, setInfo] = useState<LinkInfo | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!isUrl(url)) {
      setInfo(null);
      return;
    }
    let live = true;
    setLoading(true);
    const t = setTimeout(async () => {
      const ask = (probe: boolean) => api<LinkInfo>("/clipper/inspect", { method: "POST", json: { url: url.trim(), probe } });
      try {
        const fast = await ask(false); // platform right away
        if (!live) return;
        setInfo(fast);
        if (fast.title === undefined && fast.error === undefined) {
          const full = await ask(true); // then title/length if the site lets us look
          if (live) setInfo(full);
        }
      } catch {
        if (live) setInfo(null);
      } finally {
        if (live) setLoading(false);
      }
    }, 400);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [url]);
  return { info, loading };
}

export function LinkPreview({ info, loading }: { info: LinkInfo | null; loading: boolean }) {
  if (loading && !info) return <p className="text-xs text-muted-foreground">Checking the link…</p>;
  if (!info) return null;
  const probing = loading && info.title === undefined && info.error === undefined;
  return (
    <div className="flex gap-3 rounded-lg border bg-muted/30 p-3" data-testid="link-preview">
      {info.thumbnail && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={info.thumbnail} alt="" className="h-16 w-28 shrink-0 rounded object-cover" referrerPolicy="no-referrer" />
      )}
      <div className="min-w-0 text-sm">
        <p className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary" data-testid="platform-chip">
            <Globe className="size-3" /> {info.label}
          </span>
          {typeof info.duration === "number" && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="size-3" /> {fmtDuration(info.duration)}
            </span>
          )}
        </p>
        {info.title && <p className="mt-1 truncate font-medium">{info.title}</p>}
        {probing && <p className="mt-1 text-xs text-muted-foreground">Looking up the video…</p>}
        {info.too_long && <p className="mt-1 text-xs text-destructive">This video is longer than your plan allows. Upload a trimmed file or upgrade.</p>}
        {info.help && (
          <p className="mt-1 flex gap-1 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3 shrink-0" /> {info.help}
          </p>
        )}
      </div>
    </div>
  );
}
