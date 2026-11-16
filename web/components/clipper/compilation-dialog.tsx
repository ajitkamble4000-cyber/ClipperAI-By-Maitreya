"use client";

import { useEffect, useState } from "react";
import { Film, Loader2 } from "lucide-react";
import { toast } from "sonner";
import type { Clip } from "@/components/clipper/clip-card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { useJob } from "@/hooks/use-job";
import { api, signedUrl } from "@/lib/api";

/** Pick finished clips (in order) and join them into one video. */
export function CompilationButton({ projectId, clips }: { projectId: string; clips: Clip[] }) {
  const ready = clips.filter((c) => c.status === "ready");
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [transition, setTransition] = useState("cut");
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);

  useEffect(() => {
    if (!job) return;
    if (job.status === "succeeded" && job.result?.key) {
      toast.success("Compilation ready");
      signedUrl(String(job.result.key), String(job.result.filename ?? "compilation.mp4")).then((u) => (window.location.href = u));
      setJobId(null);
    } else if (job.status === "failed") {
      toast.error(job.error ?? "Compilation failed. Your tokens were refunded.");
      setJobId(null);
    }
  }, [job]);

  if (ready.length < 2) return null;
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const make = async () => {
    try {
      const r = await api<{ id: string }>(`/clipper/projects/${projectId}/compilation`, { method: "POST", json: { clip_ids: picked, transition } });
      setJobId(r.id);
      setOpen(false);
      toast.message("Joining clips…");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <>
      <Button variant="outline" onClick={() => (setPicked(ready.map((c) => c.id)), setOpen(true))} disabled={!!jobId} data-testid="compilation">
        {jobId ? <Loader2 className="animate-spin" /> : <Film />} {jobId ? `Joining ${job?.percent ?? 0}%` : "Compilation"}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogTitle>Make a compilation</DialogTitle>
          <DialogDescription>The picked clips are joined in the order you tick them.</DialogDescription>
          <div className="grid gap-1.5">
            {ready.map((c) => {
              const n = picked.indexOf(c.id);
              return (
                <label key={c.id} className="flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm">
                  <input type="checkbox" checked={n >= 0} onChange={() => toggle(c.id)} className="size-4" />
                  <span className="w-5 text-xs text-muted-foreground">{n >= 0 ? n + 1 : ""}</span>
                  <span className="truncate">{c.title || `Clip ${c.idx}`}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{c.aspect ?? "9:16"}</span>
                </label>
              );
            })}
          </div>
          <div className="flex items-center justify-between gap-2">
            <Select
              value={transition}
              onValueChange={setTransition}
              className="w-40"
              aria-label="Transition"
              options={[
                { value: "cut", label: "Straight cut" },
                { value: "fade", label: "Crossfade" },
              ]}
            />
            <Button onClick={make} disabled={picked.length < 2} data-testid="make-compilation">
              Join {picked.length} clips
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
