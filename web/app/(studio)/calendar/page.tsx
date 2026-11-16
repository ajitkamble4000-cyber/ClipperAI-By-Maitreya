"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CalendarSync, Check, ChevronLeft, ChevronRight, ExternalLink, SkipForward, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { PLATFORMS } from "@/components/calendar/schedule-dialog";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { href } from "@/lib/routes";

interface Item {
  id: string;
  project_id: string;
  project_type: "clip" | "story";
  project_title: string;
  clip_title: string | null;
  platform: string;
  scheduled_at: string;
  caption: string;
  status: "planned" | "posted" | "skipped";
  posted_url: string | null;
}

const P = Object.fromEntries(PLATFORMS.map((p) => [p.value, p]));
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function monthGrid(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const offset = (first.getDay() + 6) % 7; // Monday first
  return Array.from({ length: 42 }, (_, i) => new Date(year, month, 1 - offset + i));
}
const sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

export default function CalendarPage() {
  const now = new Date();
  const [cursor, setCursor] = useState({ y: now.getFullYear(), m: now.getMonth() });
  const [items, setItems] = useState<Item[]>([]);
  const [open, setOpen] = useState<Item | null>(null);
  const [postUrl, setPostUrl] = useState("");
  const days = useMemo(() => monthGrid(cursor.y, cursor.m), [cursor]);

  const load = useCallback(() => {
    const from = days[0];
    const to = new Date(days[41].getTime() + 86400000);
    api<Item[]>(`/calendar?from=${encodeURIComponent(from.toISOString())}&to=${encodeURIComponent(to.toISOString())}`)
      .then(setItems)
      .catch(() => setItems([]));
  }, [days]);
  useEffect(load, [load]);

  const upcoming = items.filter((i) => i.status === "planned" && new Date(i.scheduled_at) >= new Date(now.getTime() - 3600000)).slice(0, 8);
  const update = async (it: Item, body: Record<string, unknown>, msg: string) => {
    try {
      await api(`/calendar/${it.id}`, { method: "PATCH", json: body });
      toast.success(msg);
      setOpen(null);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const subscribe = async () => {
    try {
      const r = await api<{ url: string }>("/calendar/feed");
      await navigator.clipboard.writeText(r.url).catch(() => {});
      toast.success("Calendar link copied", { description: "Add it in Google Calendar (From URL) or Apple Calendar (New subscription)." });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const title = (i: Item) => i.clip_title || i.project_title;
  const monthName = new Date(cursor.y, cursor.m, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Calendar"
        description="Plan when each video goes out. Schedule from any finished clip or story."
        actions={
          <Button variant="outline" onClick={subscribe} data-testid="subscribe">
            <CalendarSync /> Subscribe
          </Button>
        }
      />
      <div className="grid gap-6 xl:grid-cols-[1fr_300px]">
        <div className="rounded-xl border bg-card p-3">
          <div className="mb-3 flex items-center justify-between">
            <Button size="icon" variant="ghost" aria-label="Previous month" onClick={() => setCursor((c) => (c.m === 0 ? { y: c.y - 1, m: 11 } : { y: c.y, m: c.m - 1 }))}>
              <ChevronLeft />
            </Button>
            <p className="font-medium" data-testid="month">
              {monthName}
            </p>
            <Button size="icon" variant="ghost" aria-label="Next month" onClick={() => setCursor((c) => (c.m === 11 ? { y: c.y + 1, m: 0 } : { y: c.y, m: c.m + 1 }))}>
              <ChevronRight />
            </Button>
          </div>
          <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg border bg-border text-xs">
            {DAYS.map((d) => (
              <div key={d} className="bg-muted/50 px-2 py-1 text-center font-medium text-muted-foreground">
                {d}
              </div>
            ))}
            {days.map((d) => {
              const list = items.filter((i) => sameDay(new Date(i.scheduled_at), d));
              return (
                <div key={d.toISOString()} className={cn("min-h-20 bg-card p-1", d.getMonth() !== cursor.m && "opacity-40")}>
                  <p className={cn("mb-1 text-right text-[11px]", sameDay(d, now) && "font-bold text-primary")}>{d.getDate()}</p>
                  <div className="grid gap-0.5">
                    {list.map((i) => (
                      <button
                        key={i.id}
                        type="button"
                        onClick={() => (setOpen(i), setPostUrl(i.posted_url ?? ""))}
                        className={cn("flex items-center gap-1 truncate rounded px-1 py-0.5 text-left text-[11px] hover:bg-accent", i.status !== "planned" && "line-through opacity-60")}
                        data-testid="cal-item"
                      >
                        <span className={cn("size-1.5 shrink-0 rounded-full", P[i.platform]?.color)} />
                        <span className="truncate">{title(i)}</span>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="grid content-start gap-2">
          <p className="text-sm font-medium">Coming up</p>
          {upcoming.length === 0 && <p className="text-sm text-muted-foreground">Nothing planned. Use “Schedule” on a finished clip.</p>}
          {upcoming.map((i) => (
            <button key={i.id} type="button" onClick={() => (setOpen(i), setPostUrl(""))} className="rounded-lg border p-2.5 text-left text-sm hover:border-primary/50" data-testid="upcoming">
              <span className="flex items-center gap-2">
                <span className={cn("size-2 rounded-full", P[i.platform]?.color)} />
                <span className="truncate font-medium">{title(i)}</span>
              </span>
              <span className="text-xs text-muted-foreground">
                {P[i.platform]?.label} · {new Date(i.scheduled_at).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
              </span>
            </button>
          ))}
        </div>
      </div>

      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent>
          {open && (
            <>
              <DialogTitle>{title(open)}</DialogTitle>
              <DialogDescription>
                {P[open.platform]?.label} · {new Date(open.scheduled_at).toLocaleString()} · {open.status}
              </DialogDescription>
              {open.caption && <p className="whitespace-pre-line rounded-lg border p-3 text-sm">{open.caption}</p>}
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(open.caption).then(() => toast.success("Post text copied")).catch(() => {})}>
                  Copy text
                </Button>
                <Button size="sm" variant="outline" asChild>
                  <Link href={href(`/${open.project_type === "clip" ? "clipper" : "story"}/${open.project_id}`)}>
                    <ExternalLink /> Open video
                  </Link>
                </Button>
              </div>
              {open.status === "planned" && (
                <div className="grid gap-2">
                  <div className="flex gap-2">
                    <Input value={postUrl} onChange={(e) => setPostUrl(e.target.value)} placeholder="Link to the post (optional)" aria-label="Post link" />
                    <Button onClick={() => update(open, { status: "posted", ...(postUrl.trim() ? { posted_url: postUrl.trim() } : {}) }, "Marked as posted")} data-testid="mark-posted">
                      <Check /> Posted
                    </Button>
                  </div>
                  <Button size="sm" variant="ghost" className="justify-self-start" onClick={() => update(open, { status: "skipped" }, "Skipped")}>
                    <SkipForward /> Skip
                  </Button>
                </div>
              )}
              {open.posted_url && (
                <a href={open.posted_url} target="_blank" rel="noreferrer noopener" className="text-sm text-primary underline">
                  View the post
                </a>
              )}
              <Button
                size="sm"
                variant="ghost"
                className="justify-self-start text-destructive"
                onClick={async () => {
                  await api(`/calendar/${open.id}`, { method: "DELETE" }).catch(() => {});
                  setOpen(null);
                  load();
                }}
              >
                <Trash2 /> Remove from calendar
              </Button>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
