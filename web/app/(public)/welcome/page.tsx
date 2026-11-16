"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Captions,
  Coins,
  Crop,
  Gauge,
  Globe,
  Languages,
  Layers,
  Palette,
  Scissors,
  Share2,
  Sparkles,
  Wand2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { supabaseBrowser } from "@/lib/supabase/client";

const PLATFORMS = ["YouTube", "TikTok", "Instagram", "X", "Facebook", "Vimeo", "Twitch", "Reddit", "LinkedIn", "Kick"];

const FEATURES = [
  { icon: Wand2, title: "Paste any link", body: "YouTube, TikTok, Instagram, X and more. Auto mode captions short videos and clips long ones." },
  { icon: Scissors, title: "AI clip finder", body: "Finds the moments worth posting, writes titles, hooks and hashtags, and scores each clip." },
  { icon: Captions, title: "Captions that pop", body: "Word-by-word animated captions in 8 styles, with emoji and keyword highlights." },
  { icon: Crop, title: "Smart framing", body: "Follows faces or the action. Export 9:16, 1:1, 4:5 or 16:9." },
  { icon: Gauge, title: "Tighter pacing", body: "Removes silences and filler words automatically, captions re-timed to match." },
  { icon: Languages, title: "Captions in 24 languages", body: "Translate the captions while keeping perfect timing. SRT, VTT and TXT files included." },
  { icon: Sparkles, title: "AI story videos", body: "Idea to script, images, voiceover, music and captions: a finished Short in minutes." },
  { icon: Palette, title: "Your brand", body: "Logo, @handle, colours and a progress bar on every export." },
  { icon: Layers, title: "Batch mode", body: "Drop in 25 links and come back to finished videos." },
  { icon: Share2, title: "Share links", body: "Send a private link to a client or teammate: no account needed to watch." },
  { icon: Globe, title: "Many AI providers", body: "Runs on the AI provider you choose, with automatic fallback." },
  { icon: Coins, title: "Fair tokens", body: "1,000 free tokens every day. Failed jobs are refunded automatically." },
];

export default function WelcomePage() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const go = async (e: React.FormEvent) => {
    e.preventDefault();
    const target = `/clipper/new${url.trim() ? `?url=${encodeURIComponent(url.trim())}` : ""}`;
    const { data } = await supabaseBrowser().auth.getSession();
    router.push(data.session ? target : `/signup?next=${encodeURIComponent(target)}`);
  };

  return (
    <>
      <section className="mx-auto max-w-6xl px-4 pb-16 pt-16 text-center sm:pt-24">
        <p className="mx-auto mb-4 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs text-muted-foreground">
          <Sparkles className="size-3.5 text-primary" /> 1,000 free tokens every day
        </p>
        <h1 className="mx-auto max-w-3xl text-4xl font-bold tracking-tight sm:text-6xl">
          Paste any link. <span className="text-primary">Get scroll-stopping Shorts.</span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-muted-foreground">
          Captioned clips from podcasts, streams and videos, or a whole video captioned, in the format every platform wants. Plus AI story videos
          from just an idea.
        </p>
        <form onSubmit={go} className="mx-auto mt-8 flex max-w-xl flex-col gap-2 sm:flex-row">
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=…"
            aria-label="Video link"
            className="h-12 text-base"
          />
          <Button type="submit" size="lg" className="h-12" data-testid="hero-go">
            Make Shorts <ArrowRight />
          </Button>
        </form>
        <p className="mt-6 text-xs text-muted-foreground">Works with {PLATFORMS.join(" · ")} and any direct video link</p>
      </section>

      <section className="mx-auto max-w-6xl px-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-xl border bg-card/50 p-5">
              <f.icon className="size-5 text-primary" />
              <h3 className="mt-3 font-semibold">{f.title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto mt-20 max-w-6xl px-4">
        <h2 className="text-center text-2xl font-semibold">How it works</h2>
        <ol className="mt-8 grid gap-4 sm:grid-cols-3">
          {[
            ["Paste or upload", "Any public link, or a file up to 4 GB."],
            ["Pick your style", "Clips or captions, format, language, caption look, your brand."],
            ["Download & post", "Ready-to-post MP4s with titles, hashtags and caption files."],
          ].map(([t, b], i) => (
            <li key={t} className="rounded-xl border p-5">
              <span className="flex size-8 items-center justify-center rounded-full bg-primary/15 text-sm font-semibold text-primary">{i + 1}</span>
              <h3 className="mt-3 font-semibold">{t}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{b}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mx-auto mt-20 max-w-3xl px-4 text-center">
        <h2 className="text-2xl font-semibold">Start free, upgrade when you grow</h2>
        <p className="mt-2 text-muted-foreground">Free gets you 1,000 tokens a day. Pro and Business add more tokens, no watermark and pro tools.</p>
        <div className="mt-6 flex justify-center gap-3">
          <Button asChild size="lg">
            <Link href="/signup">Create free account</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/pricing">See pricing</Link>
          </Button>
        </div>
      </section>
    </>
  );
}
