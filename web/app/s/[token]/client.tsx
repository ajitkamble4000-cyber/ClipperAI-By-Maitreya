"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Download } from "lucide-react";
import { BrandMark } from "@/components/shell/brand-mark";
import { BRAND } from "@/lib/brand";
import { env } from "@/lib/env";
import { useRouteId } from "@/lib/use-route-id";

interface Shared {
  title: string;
  description: string;
  hashtags: string[];
  aspect: string;
  video_url: string;
  poster_url: string | null;
  download_url: string;
  by: string | null;
}

async function load(token: string): Promise<Shared | null> {
  try {
    const r = await fetch(`${env.apiUrl}/public/share/${encodeURIComponent(token)}`, { cache: "no-store" });
    return r.ok ? ((await r.json()) as Shared) : null;
  } catch {
    return null;
  }
}

const RATIO: Record<string, string> = { "9:16": "aspect-[9/16] max-w-sm", "1:1": "aspect-square max-w-xl", "4:5": "aspect-[4/5] max-w-md", "16:9": "aspect-video max-w-3xl" };

/** Public page for a share link: watch and download, no account needed. */
export function SharedVideo({ token }: { token: string }) {
  const real = useRouteId(token);
  const [v, setV] = useState<Shared | null | undefined>(undefined);
  useEffect(() => {
    if (!real) return setV(null);
    let alive = true;
    load(real).then((x) => {
      if (!alive) return;
      setV(x);
      if (x) document.title = `${x.title} · ${BRAND}`;
    });
    return () => {
      alive = false;
    };
  }, [real]);
  return (
    <div className="flex min-h-dvh flex-col items-center px-4 py-8">
      <Link href="/welcome" className="mb-6 flex items-center gap-2 font-semibold">
        <BrandMark />
      </Link>
      {v === undefined ? (
        <div className="mt-20 size-8 animate-spin rounded-full border-2 border-primary border-t-transparent" aria-label="Loading" />
      ) : !v ? (
        <div className="mt-20 text-center">
          <h1 className="text-xl font-semibold">This link isn't available</h1>
          <p className="mt-2 text-sm text-muted-foreground">It may have expired or been turned off by its owner.</p>
        </div>
      ) : (
        <div className="grid w-full justify-items-center gap-4">
          <div className={`w-full overflow-hidden rounded-xl bg-black ${RATIO[v.aspect] ?? RATIO["9:16"]}`}>
            <video src={v.video_url} poster={v.poster_url ?? undefined} controls playsInline className="size-full" data-testid="shared-video" />
          </div>
          <div className="w-full max-w-xl">
            <h1 className="text-lg font-semibold" data-testid="shared-title">
              {v.title}
            </h1>
            {v.by && <p className="text-xs text-muted-foreground">Shared by {v.by}</p>}
            {v.description && <p className="mt-2 whitespace-pre-line text-sm text-muted-foreground">{v.description}</p>}
            {v.hashtags.length > 0 && <p className="mt-1 text-sm text-primary">{v.hashtags.join(" ")}</p>}
            <a href={v.download_url} className="mt-4 inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm hover:bg-accent">
              <Download className="size-4" /> Download
            </a>
          </div>
          <p className="mt-6 text-xs text-muted-foreground">
            Made with {BRAND}.{" "}
            <Link href="/signup" className="text-primary hover:underline">
              Make your own for free
            </Link>
          </p>
        </div>
      )}
    </div>
  );
}
