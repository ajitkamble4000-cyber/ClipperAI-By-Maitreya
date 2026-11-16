"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { MessageSquareQuote } from "lucide-react";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

interface Hit {
  project_id: string;
  title: string;
  type: "clip" | "story";
  snippet: string;
  at: number | null;
}

const fmt = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

/** Highlight markers come back as <<word>>; render them as <mark> without any HTML injection. */
function Snippet({ text }: { text: string }) {
  const parts = text.split(/(<<[^>]*>>)/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("<<") ? (
          <mark key={i} className="rounded bg-primary/25 px-0.5 text-foreground">
            {p.slice(2, -2)}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}

export function TranscriptSearch() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  useEffect(() => {
    if (q.trim().length < 2) return setHits(null);
    const t = setTimeout(() => api<Hit[]>(`/search/transcripts?q=${encodeURIComponent(q.trim())}`).then(setHits).catch(() => setHits([])), 300);
    return () => clearTimeout(t);
  }, [q]);
  return (
    <div className="grid gap-2" data-testid="transcript-search">
      <div className="relative">
        <MessageSquareQuote className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search what was said in your videos…" className="pl-9" aria-label="Search what was said" />
      </div>
      {hits && (
        <div className="grid gap-1.5">
          {hits.length === 0 && <p className="text-sm text-muted-foreground">Nobody said that in your videos yet.</p>}
          {hits.map((h) => (
            <Link key={h.project_id} href={`/${h.type === "clip" ? "clipper" : "story"}/${h.project_id}`} className="rounded-lg border p-2.5 text-sm hover:border-primary/50" data-testid="transcript-hit">
              <span className="flex items-center justify-between gap-2">
                <span className="truncate font-medium">{h.title}</span>
                {h.at !== null && <span className="shrink-0 text-xs tabular-nums text-primary">at {fmt(h.at)}</span>}
              </span>
              <span className="mt-0.5 block text-xs text-muted-foreground">
                <Snippet text={h.snippet} />
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
