"use client";

import { useCallback, useEffect, useState } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { supabaseBrowser } from "@/lib/supabase/client";
import { realtimeAuth } from "@/lib/supabase/realtime";

/** Rows of a table for one project, kept live with Realtime. */
export function useProjectRows<T extends { id: string }>(table: string, projectId: string, order = "idx") {
  const [rows, setRows] = useState<T[] | null>(null);
  const reload = useCallback(async () => {
    const { data } = await supabaseBrowser().from(table).select("*").eq("project_id", projectId).order(order);
    setRows((data as T[]) ?? []);
  }, [table, projectId, order]);
  useEffect(() => {
    const sb = supabaseBrowser();
    let ch: RealtimeChannel | null = null;
    let alive = true;
    reload();
    realtimeAuth(sb).then(() => {
      if (!alive) return;
      ch = sb
        .channel(`${table}-${projectId}`)
        .on("postgres_changes", { event: "*", schema: "public", table, filter: `project_id=eq.${projectId}` }, (p) => {
          if (p.eventType === "DELETE") return reload();
          const row = p.new as T;
          setRows((prev) => {
            if (!prev) return [row];
            const i = prev.findIndex((r) => r.id === row.id);
            if (i === -1) return [...prev, row].sort((a, b) => ((a as never)[order] > (b as never)[order] ? 1 : -1));
            const next = prev.slice();
            next[i] = { ...next[i], ...row };
            return next;
          });
        })
        .subscribe((s) => s === "SUBSCRIBED" && reload());
    });
    return () => {
      alive = false;
      if (ch) sb.removeChannel(ch);
    };
  }, [table, projectId, order, reload]);
  return { rows, setRows, reload };
}

export function useProject(projectId: string) {
  const [project, setProject] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    const sb = supabaseBrowser();
    let ch: RealtimeChannel | null = null;
    const load = () => sb.from("projects").select("*").eq("id", projectId).maybeSingle().then(({ data }) => setProject(data));
    load();
    realtimeAuth(sb).then(() => {
      ch = sb
        .channel(`project-${projectId}`)
        .on("postgres_changes", { event: "UPDATE", schema: "public", table: "projects", filter: `id=eq.${projectId}` }, (p) =>
          setProject(p.new as Record<string, unknown>),
        )
        .subscribe();
    });
    return () => {
      if (ch) sb.removeChannel(ch);
    };
  }, [projectId]);
  return project;
}
