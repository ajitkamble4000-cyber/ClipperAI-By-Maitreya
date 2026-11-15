"use client";

import { useEffect, useRef, useState } from "react";
import { Pause, Play, UploadCloud, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { api } from "@/lib/api";
import { ResumableUpload, type UploadInfo, type UploadProgress, type UploadPurpose } from "@/lib/upload";
import { cn, formatBytes } from "@/lib/utils";

const ACCEPT: Record<UploadPurpose, string> = {
  source: "video/mp4,video/quicktime,video/x-matroska,video/webm,.mkv,.mov,.mp4,.webm",
  voiceover: "audio/*,.mp3,.wav,.m4a",
  music: "audio/*,.mp3,.wav,.m4a,.ogg",
  sfx: "audio/*,.mp3,.wav,.m4a,.ogg",
  image: "image/png,image/jpeg,image/webp",
};

export function UploadDropzone({
  purpose,
  onComplete,
  label,
  className,
}: {
  purpose: UploadPurpose;
  onComplete: (u: UploadInfo) => void;
  label?: string;
  className?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [up, setUp] = useState<ResumableUpload | null>(null);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [state, setState] = useState<"idle" | "uploading" | "paused" | "done" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<UploadInfo[]>([]);

  useEffect(() => {
    if (purpose !== "source") return;
    api<UploadInfo[]>("/uploads").then(setPending).catch(() => {});
  }, [purpose]);

  const run = async (u: ResumableUpload) => {
    setState("uploading");
    setError(null);
    try {
      const info = await u.start();
      setState("done");
      onComplete(info);
    } catch (e) {
      if ((e as Error).name === "AbortError") setState("paused");
      else {
        setState("error");
        setError((e as Error).message);
      }
    }
  };

  const pick = (file: File | undefined) => {
    if (!file) return;
    const u = new ResumableUpload(file, purpose, setProgress);
    setUp(u);
    run(u);
  };

  const pct = progress ? (progress.loaded / progress.total) * 100 : 0;

  return (
    <div className={className}>
      {state === "idle" || state === "done" ? (
        <button
          type="button"
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            pick(e.dataTransfer.files[0]);
          }}
          className={cn(
            "flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition",
            drag ? "border-primary bg-primary/5" : "hover:border-primary/60",
          )}
        >
          <UploadCloud className="size-8 text-muted-foreground" />
          <span className="text-sm font-medium">
            {state === "done" ? `Uploaded ${up?.file.name}. Pick another file?` : label ?? "Drop a file or click to choose"}
          </span>
          <span className="text-xs text-muted-foreground">
            {purpose === "source" ? "MP4, MOV, MKV or WebM, up to 4 GB. Uploads resume if interrupted." : ACCEPT[purpose]}
          </span>
        </button>
      ) : (
        <div className="rounded-xl border p-4" data-testid="upload-progress">
          <div className="mb-2 flex items-center justify-between gap-2 text-sm">
            <span className="truncate font-medium">{up?.file.name}</span>
            <span className="tabular-nums text-muted-foreground">{pct.toFixed(0)}%</span>
          </div>
          <Progress value={pct} />
          <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {progress && `${formatBytes(progress.loaded)} of ${formatBytes(progress.total)}`}
              {state === "uploading" && progress?.bytesPerSecond ? ` · ${formatBytes(progress.bytesPerSecond)}/s` : ""}
            </span>
            <div className="flex gap-1">
              {state === "uploading" && (
                <Button size="sm" variant="ghost" onClick={() => up?.pause()}>
                  <Pause /> Pause
                </Button>
              )}
              {(state === "paused" || state === "error") && up && (
                <Button size="sm" variant="secondary" onClick={() => run(up)}>
                  <Play /> Resume
                </Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  up?.cancel();
                  setUp(null);
                  setState("idle");
                  setProgress(null);
                }}
              >
                <X /> Cancel
              </Button>
            </div>
          </div>
          {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
        </div>
      )}
      {state === "idle" && pending.length > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          Unfinished upload{pending.length > 1 ? "s" : ""}: {pending.map((p) => p.filename).join(", ")}. Choose the same
          file again to resume where it stopped.
        </p>
      )}
      <input
        ref={input}
        type="file"
        hidden
        accept={ACCEPT[purpose]}
        data-testid={`file-input-${purpose}`}
        onChange={(e) => {
          pick(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
    </div>
  );
}
