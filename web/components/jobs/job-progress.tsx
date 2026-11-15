"use client";

import { AlertTriangle, CheckCircle2, Loader2, RotateCcw, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { api } from "@/lib/api";
import type { Job } from "@/hooks/use-job";
import { cn } from "@/lib/utils";

export function JobProgress({ job, className, compact }: { job: Job | null; className?: string; compact?: boolean }) {
  if (!job) return null;
  const running = job.status === "queued" || job.status === "running";
  const retry = async () => {
    try {
      await api(`/jobs/${job.id}/retry`, { method: "POST" });
      toast.success("Retrying from the last completed step");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const cancel = async () => {
    await api(`/jobs/${job.id}/cancel`, { method: "POST" }).catch((e) => toast.error((e as Error).message));
  };
  return (
    <div className={cn("rounded-xl border bg-card p-4", className)} data-testid="job-progress" data-status={job.status}>
      <div className="flex items-center gap-3">
        {running && <Loader2 className="size-5 animate-spin text-primary" />}
        {job.status === "succeeded" && <CheckCircle2 className="size-5 text-success" />}
        {job.status === "failed" && <AlertTriangle className="size-5 text-destructive" />}
        {job.status === "canceled" && <XCircle className="size-5 text-muted-foreground" />}
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <p className="truncate text-sm font-medium">
              {job.status === "queued" ? "Waiting in queue…" : job.status === "succeeded" ? "Done" : job.step ?? job.status}
            </p>
            <span className="text-xs tabular-nums text-muted-foreground" data-testid="job-percent">
              {job.percent}%
            </span>
          </div>
          {!compact && job.message && running && <p className="truncate text-xs text-muted-foreground">{job.message}</p>}
        </div>
        {running && (
          <Button size="sm" variant="ghost" onClick={cancel}>
            Cancel
          </Button>
        )}
        {(job.status === "failed" || job.status === "canceled") && (
          <Button size="sm" variant="secondary" onClick={retry}>
            <RotateCcw /> Retry
          </Button>
        )}
      </div>
      {running && <Progress value={job.percent} className="mt-3" />}
      {job.status === "failed" && job.error && (
        <p className="mt-3 rounded-lg bg-destructive/10 p-3 text-sm text-destructive" data-testid="job-error">
          {job.error}
        </p>
      )}
    </div>
  );
}
