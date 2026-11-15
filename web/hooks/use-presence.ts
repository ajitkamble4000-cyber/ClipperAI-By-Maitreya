"use client";

import { useEffect, useState } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { supabaseBrowser } from "@/lib/supabase/client";
import { realtimeAuth } from "@/lib/supabase/realtime";

export interface Viewer {
  user_id: string;
  name: string;
}

/** Who else has this project open right now (Supabase Realtime presence). */
export function usePresence(room: string, me: Viewer) {
  const [viewers, setViewers] = useState<Viewer[]>([]);
  useEffect(() => {
    const sb = supabaseBrowser();
    let ch: RealtimeChannel | null = null;
    let alive = true;
    realtimeAuth(sb).then(() => {
      if (!alive) return;
      ch = sb.channel(`presence-${room}`, { config: { presence: { key: me.user_id } } });
      ch.on("presence", { event: "sync" }, () => {
        const state = ch!.presenceState<Viewer>();
        setViewers(Object.values(state).map((v) => v[0]).filter((v) => v.user_id !== me.user_id));
      }).subscribe((s) => s === "SUBSCRIBED" && ch!.track(me));
    });
    return () => {
      alive = false;
      if (ch) sb.removeChannel(ch);
    };
  }, [room, me.user_id, me.name]); // eslint-disable-line react-hooks/exhaustive-deps
  return viewers;
}
