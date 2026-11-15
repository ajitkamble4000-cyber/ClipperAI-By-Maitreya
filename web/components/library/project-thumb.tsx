"use client";

import { useEffect, useState } from "react";
import { Scissors, Sparkles } from "lucide-react";
import { signedUrl } from "@/lib/api";

const cache = new Map<string, string>();

export function ProjectThumb({ thumbKey, type }: { thumbKey: string | null; type: "clip" | "story" }) {
  const [url, setUrl] = useState<string | null>(thumbKey ? cache.get(thumbKey) ?? null : null);
  useEffect(() => {
    if (!thumbKey || cache.has(thumbKey)) return;
    signedUrl(thumbKey)
      .then((u) => {
        cache.set(thumbKey, u);
        setUrl(u);
      })
      .catch(() => {});
  }, [thumbKey]);
  const Icon = type === "clip" ? Scissors : Sparkles;
  return (
    <div className="relative aspect-[9/16] overflow-hidden rounded-xl border bg-gradient-to-br from-muted to-card">
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className="size-full object-cover transition group-hover:scale-[1.02]" />
      ) : (
        <Icon className="absolute left-1/2 top-1/2 size-8 -translate-x-1/2 -translate-y-1/2 text-muted-foreground/50" />
      )}
    </div>
  );
}
