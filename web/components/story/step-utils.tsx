"use client";

import { useEffect, useState } from "react";
import { JobProgress } from "@/components/jobs/job-progress";
import type { Job } from "@/hooks/use-job";
import { signedUrl } from "@/lib/api";

export function latestJob(jobs: Job[], kinds: string[], match?: (j: Job) => boolean): Job | undefined {
  return jobs.find((j) => kinds.includes(j.kind) && (!match || match(j)));
}

export function isActive(j?: Job | null): boolean {
  return !!j && (j.status === "queued" || j.status === "running");
}

export function StepJob({ job }: { job?: Job }) {
  if (!job || job.status === "succeeded" || job.status === "canceled") return null;
  return <JobProgress job={job} compact />;
}

/** Signed URL for an R2 key, refreshed when the key changes. */
export function useSigned(key: string | null | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!key) return setUrl(null);
    let alive = true;
    signedUrl(key).then((u) => alive && setUrl(u)).catch(() => {});
    return () => {
      alive = false;
    };
  }, [key]);
  return url;
}
