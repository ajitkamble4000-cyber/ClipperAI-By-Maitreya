"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Link2, Upload } from "lucide-react";
import { toast } from "sonner";
import { CaptionStylePicker } from "@/components/captions/caption-style-picker";
import { UploadDropzone } from "@/components/upload/upload-dropzone";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import type { CaptionStyle } from "@/lib/presets";
import type { UploadInfo } from "@/lib/upload";
import { cn } from "@/lib/utils";

const CONTENT = [
  { value: "podcast", label: "Podcast", hint: "Surprising claims, stories, quotable lines" },
  { value: "sports", label: "Sports & highlights", hint: "Big plays, crowd reactions, commentary peaks" },
  { value: "gaming", label: "Gaming", hint: "Clutch plays, fails, reactions" },
  { value: "interview", label: "Interview", hint: "Revealing answers, strong statements" },
  { value: "other", label: "Other", hint: "Most engaging self-contained moments" },
];

const REFRAME = [
  { value: "face", label: "Follow face", hint: "Keeps the speaker centered, smoothly" },
  { value: "action", label: "Follow action", hint: "Tracks the area with the most motion (sports)" },
  { value: "center", label: "Center crop", hint: "Static crop of the middle" },
  { value: "blur", label: "Fit + blur", hint: "Whole frame on a blurred background" },
];

export function NewClipForm() {
  const router = useRouter();
  const [source, setSource] = useState<"link" | "upload">("link");
  const [url, setUrl] = useState("");
  const [upload, setUpload] = useState<UploadInfo | null>(null);
  const [num, setNum] = useState(5);
  const [range, setRange] = useState<[number, number]>([20, 60]);
  const [contentType, setContentType] = useState("podcast");
  const [reframe, setReframe] = useState("face");
  const [language, setLanguage] = useState("auto");
  const [visual, setVisual] = useState(false);
  const [hook, setHook] = useState(true);
  const [style, setStyle] = useState<CaptionStyle>({ preset: "bold_pop" });
  const [busy, setBusy] = useState(false);

  const pickContent = (v: string) => {
    setContentType(v);
    if (v === "sports") {
      setReframe("action");
      setVisual(true);
    }
  };

  const ready = source === "link" ? /^https?:\/\/\S+$/.test(url.trim()) : !!upload;

  const submit = async () => {
    setBusy(true);
    try {
      const r = await api<{ project_id: string }>("/clipper/projects", {
        method: "POST",
        json: {
          ...(source === "link" ? { url: url.trim() } : { upload_id: upload!.id, title: upload!.filename.replace(/\.[^.]+$/, "") }),
          num_clips: num,
          min_len: range[0],
          max_len: range[1],
          content_type: contentType,
          reframe,
          caption_style: style,
          language,
          visual_analysis: visual,
          hook_overlay: hook,
        },
      });
      router.push(`/clipper/${r.project_id}`);
    } catch (e) {
      toast.error((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="grid max-w-4xl gap-6">
      <Card>
        <CardHeader>
          <CardTitle>1. Source video</CardTitle>
          <CardDescription>A YouTube (or other) link, or upload the file. Uploading always works, even when YouTube blocks server downloads.</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs value={source} onValueChange={(v) => setSource(v as "link" | "upload")}>
            <TabsList className="mb-4">
              <TabsTrigger value="link">
                <Link2 className="mr-1.5 size-4" /> Link
              </TabsTrigger>
              <TabsTrigger value="upload">
                <Upload className="mr-1.5 size-4" /> Upload
              </TabsTrigger>
            </TabsList>
            <TabsContent value="link">
              <Input placeholder="https://www.youtube.com/watch?v=…" value={url} onChange={(e) => setUrl(e.target.value)} aria-label="Video link" />
            </TabsContent>
            <TabsContent value="upload">
              <UploadDropzone purpose="source" onComplete={setUpload} />
              {upload && <p className="mt-2 text-sm text-success">Ready: {upload.filename}</p>}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>2. What to find</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-6">
          <div className="grid gap-2 sm:grid-cols-5">
            {CONTENT.map((c) => (
              <button
                type="button"
                key={c.value}
                onClick={() => pickContent(c.value)}
                className={cn("rounded-lg border p-3 text-left transition", contentType === c.value ? "border-primary bg-primary/10" : "hover:border-primary/50")}
              >
                <p className="text-sm font-medium">{c.label}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{c.hint}</p>
              </button>
            ))}
          </div>
          <div className="grid gap-6 sm:grid-cols-2">
            <Field label={`Number of clips: ${num}`}>
              <Slider min={1} max={20} step={1} value={[num]} onValueChange={([v]) => setNum(v)} aria-label="Number of clips" />
            </Field>
            <Field label={`Clip length: ${range[0]}–${range[1]} s`}>
              <Slider min={15} max={180} step={5} value={range} minStepsBetweenThumbs={1} onValueChange={(v) => setRange([v[0], v[1]])} />
            </Field>
            <Field label="Language">
              <Select
                value={language}
                onValueChange={setLanguage}
                options={[
                  { value: "auto", label: "Auto-detect" },
                  { value: "en", label: "English" },
                  { value: "hi", label: "Hindi" },
                  { value: "hinglish", label: "Hinglish" },
                ]}
              />
            </Field>
            <div className="grid gap-3">
              <label className="flex items-center justify-between gap-3 text-sm">
                <span>
                  Visual analysis
                  <span className="block text-xs text-muted-foreground">Gemini also watches the video (best for sports)</span>
                </span>
                <Switch checked={visual} onCheckedChange={setVisual} />
              </label>
              <label className="flex items-center justify-between gap-3 text-sm">
                <span>
                  Hook text overlay
                  <span className="block text-xs text-muted-foreground">Big text for the first 3 seconds</span>
                </span>
                <Switch checked={hook} onCheckedChange={setHook} />
              </label>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>3. Vertical framing</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 sm:grid-cols-4">
          {REFRAME.map((r) => (
            <button
              type="button"
              key={r.value}
              onClick={() => setReframe(r.value)}
              className={cn("rounded-lg border p-3 text-left transition", reframe === r.value ? "border-primary bg-primary/10" : "hover:border-primary/50")}
            >
              <p className="text-sm font-medium">{r.label}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">{r.hint}</p>
            </button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>4. Captions</CardTitle>
        </CardHeader>
        <CardContent>
          <CaptionStylePicker value={style} onChange={setStyle} hook={hook ? "You won't believe this" : null} />
        </CardContent>
      </Card>

      <div className="sticky bottom-20 z-10 flex justify-end md:bottom-4">
        <Button size="lg" onClick={submit} disabled={!ready || busy} className="shadow-xl" data-testid="create-clips">
          {busy ? "Starting…" : `Make ${num} clip${num > 1 ? "s" : ""}`}
        </Button>
      </div>
    </div>
  );
}
