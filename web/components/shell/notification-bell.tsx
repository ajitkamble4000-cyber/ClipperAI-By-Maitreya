"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { Bell, CheckCheck } from "lucide-react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { api } from "@/lib/api";
import { supabaseBrowser } from "@/lib/supabase/client";
import { realtimeAuth } from "@/lib/supabase/realtime";
import { cn, timeAgo } from "@/lib/utils";

interface Note {
  id: string;
  kind: "info" | "success" | "error" | "tokens";
  title: string;
  body: string;
  link: string | null;
  read_at: string | null;
  created_at: string;
}

const DOT: Record<Note["kind"], string> = { info: "bg-primary", success: "bg-success", error: "bg-destructive", tokens: "bg-warning" };

/** The bell: unread count (live over Realtime) and the latest notifications. */
export function NotificationBell({ className, align = "right" }: { className?: string; align?: "left" | "right" }) {
  const [items, setItems] = useState<Note[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const uid = useId(); // each bell (sidebar, phone header) needs its own Realtime channel

  const load = useCallback(() => {
    api<{ unread: number; items: Note[] }>("/notifications?limit=20")
      .then((r) => {
        setItems(r.items);
        setUnread(r.unread);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const sb = supabaseBrowser();
    let ch: RealtimeChannel | null = null;
    let alive = true;
    load();
    realtimeAuth(sb).then(() => {
      if (!alive) return;
      ch = sb.channel(`notifications${uid}`).on("postgres_changes", { event: "*", schema: "public", table: "notifications" }, load).subscribe();
    });
    return () => {
      alive = false;
      if (ch) sb.removeChannel(ch);
    };
  }, [load, uid]);

  useEffect(() => {
    const sync = () => load();
    window.addEventListener("notifications-read", sync);
    return () => window.removeEventListener("notifications-read", sync);
  }, [load]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const markRead = async () => {
    setUnread(0);
    await api("/notifications/read", { method: "POST" }).catch(() => {});
    window.dispatchEvent(new Event("notifications-read")); // the other bell updates too

  };

  return (
    <div className={cn("relative", className)} ref={box}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={unread ? `Notifications (${unread} unread)` : "Notifications"}
        className="relative rounded-lg p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
        data-testid="bell"
      >
        <Bell className="size-4" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-primary px-1 text-center text-[10px] font-semibold leading-4 text-primary-foreground" data-testid="bell-count">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div
          className={cn(
            "absolute z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border bg-popover p-2 shadow-xl",
            align === "right" ? "right-0" : "left-0",
          )}
          role="dialog"
          aria-label="Notifications"
        >
          <div className="flex items-center justify-between px-2 py-1">
            <p className="text-sm font-semibold">Notifications</p>
            {unread > 0 && (
              <button type="button" onClick={markRead} className="flex items-center gap-1 text-xs text-primary hover:underline">
                <CheckCheck className="size-3.5" /> Mark all read
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-2 py-6 text-center text-sm text-muted-foreground">Nothing yet. We'll let you know when videos are ready.</p>
            ) : (
              items.map((n) => {
                const inner = (
                  <div className={cn("flex gap-2 rounded-lg px-2 py-2 text-sm hover:bg-accent", !n.read_at && "bg-primary/5")}>
                    <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read_at ? "bg-muted" : DOT[n.kind])} />
                    <span className="min-w-0">
                      <span className="block font-medium">{n.title}</span>
                      {n.body && <span className="line-clamp-2 block text-xs text-muted-foreground">{n.body}</span>}
                      <span className="block text-[11px] text-muted-foreground">{timeAgo(n.created_at)}</span>
                    </span>
                  </div>
                );
                return n.link ? (
                  <Link key={n.id} href={n.link} onClick={() => setOpen(false)}>
                    {inner}
                  </Link>
                ) : (
                  <div key={n.id}>{inner}</div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
