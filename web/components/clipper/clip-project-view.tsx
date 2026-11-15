"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, FileArchive, Info, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { JobProgress } from "@/components/jobs/job-progress";
import { useMe } from "@/components/shell/member-context";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useJob, useProjectJobs } from "@/hooks/use-job";
import { useProject, useProjectRows } from "@/hooks/use-rows";
import { api, signedUrl } from "@/lib/api";
import { ClipCard, type Clip } from "./clip-card";

export function ClipProjectView({ projectId }: { projectId: string }) {
  const router = useRouter();
  const me = useMe();
  const project = useProject(projectId);
  const { rows: clips } = useProjectRows<Clip>("clips", projectId);
  const jobs = useProjectJobs(projectId);
  const mainJob = useMemo(() => jobs.find((j) => j.kind === "clip") ?? null, [jobs]);
  const liveMain = useJob(mainJob?.id);
  const [zipJobId, setZipJobId] = useState<string | null>(null);
  const zipJob = useJob(zipJobId);

  useEffect(() => {
    if (zipJob?.status === "succeeded" && zipJob.result?.key) {
      signedUrl(String(zipJob.result.key), String(zipJob.result.filename ?? "clips.zip")).then((u) => (window.location.href = u));
      setZipJobId(null);
    }
    if (zipJob?.status === "failed") {
      toast.error(zipJob.error ?? "ZIP failed");
      setZipJobId(null);
    }
  }, [zipJob]);

  const generating = liveMain && (liveMain.status === "queued" || liveMain.status === "running");
  const meta = (project?.meta ?? {}) as { mode?: string; options?: Record<string, unknown> };
  const basicReason = liveMain?.result?.basic_reason as string | undefined;
  const readyCount = clips?.filter((c) => c.status === "ready").length ?? 0;

  const zip = async () => {
    try {
      const j = await api<{ id: string }>(`/projects/${projectId}/zip`, { method: "POST" });
      setZipJobId(j.id);
      toast.message("Preparing ZIP…");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const remove = async () => {
    if (!confirm("Delete this project and all its clips?")) return;
    try {
      await api(`/projects/${projectId}`, { method: "DELETE" });
      router.replace("/clipper");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  if (project === null) return <Skeleton className="h-40" />;

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link href="/clipper" className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-4" /> Clipper
          </Link>
          <h1 className="truncate text-2xl font-semibold tracking-tight" data-testid="project-title">
            {String(project.title ?? "")}
          </h1>
          <p className="text-sm text-muted-foreground">
            {meta.options?.content_type ? `${String(meta.options.content_type)} · ` : ""}
            {clips ? `${readyCount}/${clips.length} clips ready` : ""}
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={zip} disabled={!readyCount || !!zipJobId} data-testid="zip">
            <FileArchive /> {zipJobId ? `Zipping ${zipJob?.percent ?? 0}%` : "Download all (ZIP)"}
          </Button>
          {(me.role === "admin" || project.created_by === me.user_id) && (
            <Button variant="ghost" size="icon" onClick={remove} aria-label="Delete project">
              <Trash2 />
            </Button>
          )}
        </div>
      </div>

      {liveMain && (generating || liveMain.status === "failed") && <JobProgress job={liveMain} />}
      {meta.mode === "basic" && !generating && (
        <div className="flex gap-2 rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-warning" />
          <span>
            These clips were picked in <b>basic mode</b> (speech density and loudness) because{" "}
            {basicReason ?? "Gemini wasn't available"}. Titles are simple; edit them before posting.
          </span>
        </div>
      )}

      {clips === null ? (
        <Skeleton className="h-72" />
      ) : clips.length === 0 && generating ? (
        <p className="text-sm text-muted-foreground">Clips will appear here as soon as the best moments are found.</p>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {clips.map((c) => (
            <ClipCard key={c.id} clip={c} locked={!!generating} />
          ))}
        </div>
      )}
    </div>
  );
}
