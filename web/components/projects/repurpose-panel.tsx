"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, ChevronDown, Copy, Download, Loader2, PenLine } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useJob } from "@/hooks/use-job";
import { api, downloadFrom } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Repurposed {
  summary?: string;
  chapters_text?: string;
  quotes?: string[];
  blog_post?: string;
  x_thread?: string[];
  linkedin_post?: string;
  newsletter?: string;
  keywords?: string[];
}

function Section({ title, text, testId }: { title: string; text: string; testId?: string }) {
  const [done, setDone] = useState(false);
  return (
    <div className="rounded-lg border p-3" data-testid={testId}>
      <div className="mb-1 flex items-center justify-between">
        <p className="text-sm font-medium">{title}</p>
        <button
          type="button"
          aria-label={`Copy ${title}`}
          className="rounded p-1 text-muted-foreground hover:text-foreground"
          onClick={() =>
            navigator.clipboard
              .writeText(text)
              .then(() => {
                setDone(true);
                setTimeout(() => setDone(false), 1200);
              })
              .catch(() => {})
          }
        >
          {done ? <Check className="size-4 text-success" /> : <Copy className="size-4" />}
        </button>
      </div>
      <p className="whitespace-pre-line text-sm text-muted-foreground">{text}</p>
    </div>
  );
}

/** Turn a video into writing: summary, YouTube chapters, quotes, blog post, X thread, LinkedIn post, newsletter. */
export function RepurposePanel({ projectId, title }: { projectId: string; title: string }) {
  const [r, setR] = useState<Repurposed | null>(null);
  const [open, setOpen] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);
  const load = useCallback(() => api<Repurposed>(`/projects/${projectId}/repurpose`).then(setR).catch(() => {}), [projectId]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (job?.status === "succeeded") {
      setJobId(null);
      load().then(() => setOpen(true));
      toast.success("Your write-up is ready");
    } else if (job?.status === "failed") {
      setJobId(null);
      toast.error(job.error ?? "Couldn't write it up. Your tokens were refunded.");
    }
  }, [job, load]);

  const has = !!r?.summary;
  const start = async () => {
    try {
      const j = await api<{ id: string }>(`/projects/${projectId}/repurpose`, { method: "POST" });
      setJobId(j.id);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="rounded-xl border bg-card" data-testid="repurpose">
      <div className="flex flex-wrap items-center gap-3 p-4">
        <PenLine className="size-5 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="font-medium">Repurpose into writing</p>
          <p className="text-xs text-muted-foreground">Summary, YouTube chapters, quotes, blog post, X thread, LinkedIn post and newsletter.</p>
        </div>
        {has && (
          <Button variant="ghost" size="sm" onClick={() => downloadFrom(`/projects/${projectId}/repurpose.md`, `${title}.md`).catch((e) => toast.error((e as Error).message))}>
            <Download /> .md
          </Button>
        )}
        <Button size="sm" variant={has ? "outline" : "default"} onClick={start} disabled={!!jobId} data-testid="write-it-up">
          {jobId ? <Loader2 className="animate-spin" /> : null} {jobId ? "Writing…" : has ? "Rewrite" : "Write it up"}
        </Button>
        {has && (
          <Button size="icon" variant="ghost" onClick={() => setOpen((o) => !o)} aria-label={open ? "Hide write-up" : "Show write-up"}>
            <ChevronDown className={cn("transition", open && "rotate-180")} />
          </Button>
        )}
      </div>
      {has && open && r && (
        <div className="grid gap-3 border-t p-4 lg:grid-cols-2">
          {r.summary && <Section title="Summary" text={r.summary} testId="rp-summary" />}
          {r.chapters_text && <Section title="YouTube chapters" text={r.chapters_text} testId="rp-chapters" />}
          {r.quotes?.length ? <Section title="Quotes" text={r.quotes.map((q) => `“${q}”`).join("\n")} /> : null}
          {r.x_thread?.length ? <Section title="X thread" text={r.x_thread.join("\n\n")} /> : null}
          {r.linkedin_post && <Section title="LinkedIn post" text={r.linkedin_post} />}
          {r.newsletter && <Section title="Newsletter" text={r.newsletter} />}
          {r.blog_post && (
            <div className="lg:col-span-2">
              <Section title="Blog post (Markdown)" text={r.blog_post} />
            </div>
          )}
          {r.keywords?.length ? <p className="text-xs text-muted-foreground lg:col-span-2">Keywords: {r.keywords.join(", ")}</p> : null}
        </div>
      )}
    </div>
  );
}
