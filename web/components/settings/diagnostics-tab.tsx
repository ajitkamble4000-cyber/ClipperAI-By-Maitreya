"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { JobProgress } from "@/components/jobs/job-progress";
import { UploadDropzone } from "@/components/upload/upload-dropzone";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useJob } from "@/hooks/use-job";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/utils";

export function DiagnosticsTab() {
  const params = useSearchParams();
  const [jobId, setJobId] = useState<string | null>(params.get("job"));
  const job = useJob(jobId);
  const [uploaded, setUploaded] = useState<string | null>(null);

  const start = async () => {
    try {
      const j = await api<{ id: string }>("/jobs/dummy", { method: "POST", json: { seconds_per_step: 2 } });
      setJobId(j.id);
      window.history.replaceState(null, "", `/settings?tab=diagnostics&job=${j.id}`);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="grid max-w-3xl gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Job queue</CardTitle>
          <CardDescription>Runs a test job on a worker. Progress should update live, even in another tab.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <Button onClick={start} className="w-fit" data-testid="run-dummy">
            Run test job
          </Button>
          <JobProgress job={job} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Storage upload</CardTitle>
          <CardDescription>Uploads straight from your browser to storage, in resumable parts.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <UploadDropzone purpose="source" onComplete={(u) => setUploaded(`${u.filename} (${formatBytes(u.size)})`)} />
          {uploaded && (
            <p className="text-sm text-success" data-testid="upload-done">
              Upload complete: {uploaded}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
