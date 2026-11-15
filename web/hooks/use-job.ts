"use client";

import { useEffect, useState } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { supabaseBrowser } from "@/lib/supabase/client";
import { realtimeAuth } from "@/lib/supabase/realtime";

export interface Job {
  id: string;
  project_id: string | null;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled";
  step: string | null;
  percent: number;
  message: string | null;
  error: string | null;
  params: Record<string, unknown>;
  result: Record<string, unknown>;
  created_at: string;
  finished_at: string | null;
}

const ACTIVE = new Set(["queued", "running"]);

/** A job row kept live with Supabase Realtime (plus a slow poll as a safety net). Survives refreshes. */
export function useJob(jobId: string | null | undefined) {
  const [job, setJob] = useState<Job | null>(null);
  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }
    const sb = supabaseBrowser();
    let alive = true;
    let ch: RealtimeChannel | null = null;
    let last: Job | null = null;
    const apply = (j: Job | null) => {
      if (alive && j) {
        last = j;
        setJob(j);
      }
    };
    const fetchNow = () => sb.from("jobs").select("*").eq("id", jobId).maybeSingle().then(({ data }) => apply(data as Job));
    (async () => {
      await realtimeAuth(sb);
      if (!alive) return;
      ch = sb
        .channel(`job-${jobId}`)
        .on("postgres_changes", { event: "UPDATE", schema: "public", table: "jobs", filter: `id=eq.${jobId}` }, (p) =>
          apply(p.new as Job),
        )
        .subscribe((status) => status === "SUBSCRIBED" && fetchNow());
      fetchNow();
    })();
    const poll = setInterval(() => {
      if (!last || ACTIVE.has(last.status)) fetchNow();
    }, 5000);
    return () => {
      alive = false;
      clearInterval(poll);
      if (ch) sb.removeChannel(ch);
    };
  }, [jobId]);
  return job;
}

/** Latest jobs for a project, live. */
export function useProjectJobs(projectId: string | null | undefined) {
  const [jobs, setJobs] = useState<Job[]>([]);
  useEffect(() => {
    if (!projectId) return;
    const sb = supabaseBrowser();
    let alive = true;
    let ch: RealtimeChannel | null = null;
    const load = () =>
      sb
        .from("jobs")
        .select("*")
        .eq("project_id", projectId)
        .order("created_at", { ascending: false })
        .limit(20)
        .then(({ data }) => alive && data && setJobs(data as Job[]));
    (async () => {
      await realtimeAuth(sb);
      if (!alive) return;
      ch = sb
        .channel(`project-jobs-${projectId}`)
        .on("postgres_changes", { event: "*", schema: "public", table: "jobs", filter: `project_id=eq.${projectId}` }, load)
        .subscribe((s) => s === "SUBSCRIBED" && load());
    })();
    const poll = setInterval(load, 10000);
    return () => {
      alive = false;
      clearInterval(poll);
      if (ch) sb.removeChannel(ch);
    };
  }, [projectId]);
  return jobs;
}
