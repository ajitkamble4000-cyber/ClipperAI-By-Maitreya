"use client";

import { useCallback, useEffect, useState } from "react";
import { Music, Play, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { UploadDropzone } from "@/components/upload/upload-dropzone";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api, signedUrl } from "@/lib/api";
import { MUSIC_MOODS } from "@/lib/story";
import { supabaseBrowser } from "@/lib/supabase/client";
import type { UploadInfo } from "@/lib/upload";

interface Row {
  id: string;
  name: string;
  r2_key?: string;
  mood?: string;
  tag?: string;
  prompt?: string;
  builtin?: boolean;
}

function useTable(table: string, order: string) {
  const [rows, setRows] = useState<Row[]>([]);
  const load = useCallback(() => {
    supabaseBrowser().from(table).select("*").order(order).then(({ data }) => setRows((data as Row[]) ?? []));
  }, [table, order]);
  useEffect(load, [load]);
  return { rows, load };
}

async function play(key?: string) {
  if (key) new Audio(await signedUrl(key)).play().catch(() => {});
}

function AudioLibrary({ kind }: { kind: "music" | "sfx" }) {
  const { rows, load } = useTable(kind === "music" ? "music_tracks" : "sfx", kind === "music" ? "mood" : "tag");
  const [upload, setUpload] = useState<UploadInfo | null>(null);
  const [name, setName] = useState("");
  const [label, setLabel] = useState(kind === "music" ? "suspense" : "");
  const add = async () => {
    if (!upload) return;
    try {
      await api(`/library/${kind}`, {
        method: "POST",
        json: kind === "music" ? { upload_id: upload.id, name, mood: label } : { upload_id: upload.id, name, tag: label.toLowerCase() },
      });
      setUpload(null);
      setName("");
      load();
      toast.success("Added");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>{kind === "music" ? "Music library" : "Sound effects"}</CardTitle>
        <CardDescription>
          {kind === "music"
            ? "Royalty-free tracks tagged by mood. Stories pick one automatically by genre, or editors choose one."
            : "Placed at scene cuts or when a scene's SFX suggestion mentions the tag (e.g. whoosh, boom, heartbeat). A small built-in kit is created automatically."}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid gap-2">
          {rows.length === 0 && <p className="text-sm text-muted-foreground">Nothing here yet.</p>}
          {rows.map((r) => (
            <div key={r.id} className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm">
              <span className="flex min-w-0 items-center gap-2">
                <Music className="size-4 shrink-0 text-muted-foreground" />
                <span className="truncate">{r.name}</span>
                <span className="rounded bg-muted px-1.5 text-xs text-muted-foreground">{r.mood ?? r.tag}</span>
              </span>
              <span className="flex gap-1">
                <Button size="icon" variant="ghost" aria-label={`Play ${r.name}`} onClick={() => play(r.r2_key)}>
                  <Play />
                </Button>
                <Button size="icon" variant="ghost" aria-label={`Delete ${r.name}`} onClick={() => api(`/library/${kind}/${r.id}`, { method: "DELETE" }).then(load)}>
                  <Trash2 />
                </Button>
              </span>
            </div>
          ))}
        </div>
        <div className="grid gap-3 rounded-lg border p-3">
          <UploadDropzone purpose={kind} onComplete={(u) => { setUpload(u); setName(u.filename.replace(/\.[^.]+$/, "")); }} label={`Add ${kind === "music" ? "a track" : "a sound"}`} />
          {upload && (
            <div className="grid gap-2 sm:grid-cols-[1fr_180px_auto] sm:items-end">
              <Field label="Name">
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              {kind === "music" ? (
                <Field label="Mood">
                  <Select value={label} onValueChange={setLabel} options={MUSIC_MOODS.map((m) => ({ value: m, label: m }))} />
                </Field>
              ) : (
                <Field label="Tag">
                  <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="whoosh" />
                </Field>
              )}
              <Button onClick={add} disabled={!name || !label}>
                Save
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function StylesLibrary() {
  const { rows, load } = useTable("visual_styles", "name");
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [example, setExample] = useState<UploadInfo | null>(null);
  const add = async () => {
    try {
      await api("/library/styles", { method: "POST", json: { name, prompt, example_upload_id: example?.id ?? null } });
      setName("");
      setPrompt("");
      setExample(null);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>Visual styles</CardTitle>
        <CardDescription>The style prompt is added to every scene image. Add your channel's own look.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {rows.map((r) => (
          <div key={r.id} className="flex items-start justify-between gap-2 rounded-lg border px-3 py-2 text-sm">
            <span className="min-w-0">
              <span className="font-medium">{r.name}</span> {r.builtin && <span className="text-xs text-muted-foreground">(built-in)</span>}
              <span className="block truncate text-xs text-muted-foreground">{r.prompt}</span>
            </span>
            {!r.builtin && (
              <Button size="icon" variant="ghost" aria-label={`Delete ${r.name}`} onClick={() => api(`/library/styles/${r.id}`, { method: "DELETE" }).then(load)}>
                <Trash2 />
              </Button>
            )}
          </div>
        ))}
        <div className="grid gap-2 rounded-lg border p-3">
          <Input placeholder="Style name (e.g. Retro VHS)" value={name} onChange={(e) => setName(e.target.value)} aria-label="Style name" />
          <Textarea placeholder="Style prompt: medium, lighting, palette, texture, camera…" value={prompt} onChange={(e) => setPrompt(e.target.value)} aria-label="Style prompt" />
          <UploadDropzone purpose="image" onComplete={setExample} label="Optional example image" />
          <Button className="w-fit" onClick={add} disabled={name.length < 2 || prompt.length < 10}>
            Add style
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function LibraryTab() {
  return (
    <div className="grid max-w-3xl gap-6">
      <AudioLibrary kind="music" />
      <AudioLibrary kind="sfx" />
      <StylesLibrary />
    </div>
  );
}
