"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { supabaseBrowser } from "@/lib/supabase/client";

type State = "idle" | "saving" | "saved" | "error";
export const SaveStateContext = createContext<(delta: number, error?: boolean) => void>(() => {});

/** Shared "Saving… / Saved" indicator for every autosaving field on the page. */
export function useSaveIndicator() {
  const [pending, setPending] = useState(0);
  const [state, setState] = useState<State>("idle");
  const report = useCallback((delta: number, error?: boolean) => {
    setPending((p) => {
      const n = Math.max(0, p + delta);
      setState(error ? "error" : n > 0 ? "saving" : "saved");
      return n;
    });
  }, []);
  return { state, pending, report };
}

/** Debounced partial updates to one row; flushes on unmount and when the tab is hidden. */
export function useAutosave(table: string, match: Record<string, string>, delay = 700) {
  const report = useContext(SaveStateContext);
  const patch = useRef<Record<string, unknown>>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const matchKey = JSON.stringify(match);

  const flush = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    const body = patch.current;
    if (!Object.keys(body).length) return;
    patch.current = {};
    report(1);
    let q = supabaseBrowser().from(table).update(body);
    for (const [k, v] of Object.entries(JSON.parse(matchKey) as Record<string, string>)) q = q.eq(k, v);
    const { error } = await q;
    report(-1, !!error);
  }, [table, matchKey, report]);

  const save = useCallback(
    (p: Record<string, unknown>) => {
      patch.current = { ...patch.current, ...p };
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(flush, delay);
    },
    [flush, delay],
  );

  useEffect(() => {
    const onHide = () => document.visibilityState === "hidden" && flush();
    document.addEventListener("visibilitychange", onHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      flush();
    };
  }, [flush]);

  return { save, flush };
}
