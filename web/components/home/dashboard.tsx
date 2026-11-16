"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, CalendarDays, Captions, CheckCircle2, Circle, Coins, Infinity as InfinityIcon, Loader2, Megaphone, Scissors, Sparkles, Wand2 } from "lucide-react";
import { ProjectThumb } from "@/components/library/project-thumb";
import { useMe } from "@/components/shell/member-context";
import { useWallet, type Wallet } from "@/components/shell/token-chip";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import { href } from "@/lib/routes";

interface Recent {
  id: string;
  type: "clip" | "story";
  title: string;
  status: string;
  thumbnail_key: string | null;
  updated_at: string;
  tool: string | null;
  ready_clips: number;
}
interface Data {
  wallet: Wallet;
  recent: Recent[];
  running_jobs: number;
  spent_7d: number;
  checklist: { id: string; label: string; done: boolean; href: string }[];
  pending_upgrade: { plan_id: string } | null;
  announcements: { id: string; message: string; level: string }[];
}

function hoursUntil(iso: string) {
  const h = Math.max(0, (new Date(iso).getTime() - Date.now()) / 3_600_000);
  return h < 1 ? `${Math.max(1, Math.round(h * 60))} min` : `${Math.floor(h)} h ${Math.round((h % 1) * 60)} min`;
}

export function Dashboard() {
  const me = useMe();
  const router = useRouter();
  const [data, setData] = useState<Data | null>(null);
  const [url, setUrl] = useState("");
  const wallet = useWallet(me.wallet);

  useEffect(() => {
    api<Data>("/me/dashboard").then(setData).catch(() => {});
  }, []);

  const go = (mode: string) => (e?: React.FormEvent) => {
    e?.preventDefault();
    const q = new URLSearchParams({ mode });
    if (url.trim()) q.set("url", url.trim());
    router.push(`/clipper/new?${q}`);
  };

  const first = (me.display_name ?? "").split(" ")[0];
  const todo = data?.checklist.filter((c) => !c.done) ?? [];
  const pct = me.wallet.daily_allowance ? Math.min(100, Math.round(((wallet?.daily_balance ?? 0) / me.wallet.daily_allowance) * 100)) : 100;

  return (
    <div className="grid gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Home</h1>
        <p className="mt-1 text-sm text-muted-foreground">{first ? `Welcome back, ${first}.` : "Welcome back."} What are we making today?</p>
      </div>

      {data?.announcements.map((a) => (
        <div key={a.id} className={cn("flex gap-2 rounded-xl border p-3 text-sm", a.level === "warning" ? "border-warning/40 bg-warning/10" : "bg-primary/5")}>
          <Megaphone className="mt-0.5 size-4 shrink-0 text-primary" /> {a.message}
        </div>
      ))}

      <Card>
        <CardContent className="grid gap-3 p-5">
          <form onSubmit={go("auto")} className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Paste a YouTube, TikTok, Instagram, X… link"
              aria-label="Quick link"
              className="h-11"
              data-testid="quick-link"
            />
            <Button type="submit" size="lg" className="h-11" data-testid="quick-go">
              <Wand2 /> Make Shorts
            </Button>
          </form>
          <div className="flex flex-wrap gap-2 text-sm">
            <Button variant="outline" size="sm" onClick={() => go("clips")()}>
              <Scissors /> Find clips
            </Button>
            <Button variant="outline" size="sm" onClick={() => go("captions")()}>
              <Captions /> Caption a video
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link href="/story/new">
                <Sparkles /> AI story
              </Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link href="/calendar">
                <CalendarDays /> Calendar
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        <Card data-testid="wallet-card">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              {wallet?.unlimited ? <InfinityIcon className="size-4 text-primary" /> : <Coins className="size-4 text-primary" />} Tokens
            </CardTitle>
          </CardHeader>
          <CardContent>
            {wallet?.unlimited ? (
              <p className="text-2xl font-semibold">Unlimited</p>
            ) : (
              <>
                <p className="text-2xl font-semibold tabular-nums">{(wallet?.total ?? me.wallet.total).toLocaleString()}</p>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {wallet?.bonus_balance ? `${wallet.bonus_balance.toLocaleString()} bonus · ` : ""}+{me.wallet.daily_allowance?.toLocaleString()} in{" "}
                  {hoursUntil(wallet?.resets_at ?? me.wallet.resets_at)}
                </p>
              </>
            )}
            <Link href="/account/tokens" className="mt-3 inline-flex items-center gap-1 text-xs text-primary hover:underline">
              History <ArrowRight className="size-3" />
            </Link>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Your plan</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{me.unlimited ? (me.team ? `${me.team[0].toUpperCase()}${me.team.slice(1)} team` : "Owner") : me.plan.name}</p>
            <p className="mt-2 text-xs text-muted-foreground">
              {data ? `${data.spent_7d.toLocaleString()} tokens used in the last 7 days` : " "}
              {data?.running_jobs ? ` · ${data.running_jobs} running now` : ""}
            </p>
            {!me.unlimited && (
              <Link href="/pricing" className="mt-3 inline-flex items-center gap-1 text-xs text-primary hover:underline">
                {data?.pending_upgrade ? "Upgrade requested" : me.plan_id === "business" ? "Compare plans" : "Upgrade"} <ArrowRight className="size-3" />
              </Link>
            )}
          </CardContent>
        </Card>
        <Card data-testid="checklist">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {todo.length ? `Getting started · ${data!.checklist.length - todo.length}/${data!.checklist.length}` : "You're all set"}
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-1.5">
            {data ? (
              data.checklist.map((c) => (
                <Link key={c.id} href={c.href} className={cn("flex items-center gap-2 text-sm", c.done ? "text-muted-foreground line-through" : "hover:text-primary")}>
                  {c.done ? <CheckCircle2 className="size-4 shrink-0 text-success" /> : <Circle className="size-4 shrink-0 text-muted-foreground" />}
                  {c.label}
                </Link>
              ))
            ) : (
              <Skeleton className="h-20" />
            )}
          </CardContent>
        </Card>
      </div>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">Recent</h2>
          <Link href="/library" className="text-sm text-primary hover:underline">
            See all
          </Link>
        </div>
        {!data ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="aspect-[9/16]" />
            ))}
          </div>
        ) : data.recent.length === 0 ? (
          <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
            Nothing yet. Paste a link above to make your first Shorts.
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6" data-testid="recent">
            {data.recent.map((r) => (
              <Link key={r.id} href={href(`/${r.type === "clip" ? "clipper" : "story"}/${r.id}`)} className="group">
                <ProjectThumb thumbKey={r.thumbnail_key} type={r.type} />
                <p className="mt-2 truncate text-sm font-medium">{r.title}</p>
                <p className="flex items-center gap-1 text-xs text-muted-foreground">
                  {["processing", "rendering"].includes(r.status) && <Loader2 className="size-3 animate-spin" />}
                  {r.type === "clip" ? (r.tool === "captions" ? "Captions" : `${r.ready_clips} clip${r.ready_clips === 1 ? "" : "s"}`) : "Story"} ·{" "}
                  {timeAgo(r.updated_at)}
                </p>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
