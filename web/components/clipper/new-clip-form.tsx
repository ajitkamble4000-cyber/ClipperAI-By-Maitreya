"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Captions, Coins, Layers, Link2, Scissors, Sparkles, Upload, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { CaptionStylePicker } from "@/components/captions/caption-style-picker";
import { MUSIC_MOODS } from "@/components/clipper/clip-tools";
import { LinkPreview, isUrl, useLinkInfo } from "@/components/clipper/link-inspector";
import { LockedBadge, useGate } from "@/components/plan/locked";
import { TemplateBar } from "@/components/plan/template-bar";
import { UploadDropzone } from "@/components/upload/upload-dropzone";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import type { CaptionStyle } from "@/lib/presets";
import type { UploadInfo } from "@/lib/upload";
import { cn } from "@/lib/utils";
import { href } from "@/lib/routes";

type Mode = "auto" | "clips" | "captions";
type Aspect = "9:16" | "1:1" | "4:5" | "16:9";

interface Options {
  languages: { code: string; name: string }[];
  aspects: { id: Aspect; label: string; hint: string; locked: boolean }[];
  max_batch: number;
  max_clips: number;
  captions_max_minutes: number;
}

interface Quote {
  tokens: number;
  balance: number;
  unlimited: boolean;
  enough: boolean;
}

const MODES: { id: Mode; label: string; hint: string; icon: typeof Wand2 }[] = [
  { id: "auto", label: "Auto", hint: "Short video? Captioned whole. Long? The best clips.", icon: Wand2 },
  { id: "clips", label: "Clips", hint: "Find the best moments and cut them into Shorts", icon: Scissors },
  { id: "captions", label: "Captions", hint: "Caption the whole video, nothing cut", icon: Captions },
];

const CONTENT = [
  { value: "podcast", label: "Podcast", hint: "Surprising claims, stories, quotable lines" },
  { value: "interview", label: "Interview", hint: "Revealing answers, strong statements" },
  { value: "sports", label: "Sports", hint: "Big plays, crowd reactions, commentary peaks" },
  { value: "gaming", label: "Gaming", hint: "Clutch plays, fails, reactions" },
  { value: "education", label: "Education", hint: "Clear explanations, aha moments, tips" },
  { value: "vlog", label: "Vlog", hint: "Funny, emotional and relatable moments" },
  { value: "other", label: "Other", hint: "Most engaging self-contained moments" },
];

const REFRAME = [
  { value: "face", label: "Follow face", hint: "Keeps the speaker centered, smoothly" },
  { value: "action", label: "Follow action", hint: "Tracks the area with the most motion" },
  { value: "center", label: "Center crop", hint: "Static crop of the middle" },
  { value: "blur", label: "Fit + blur", hint: "Whole frame on a blurred background" },
  { value: "split", label: "Split screen", hint: "Two people talking: one on top, one below" },
];

const ASPECT_BOX: Record<Aspect, string> = { "9:16": "h-8 w-[18px]", "1:1": "size-7", "4:5": "h-8 w-[26px]", "16:9": "h-[18px] w-8" };

function Choice({
  active,
  onClick,
  children,
  testId,
  className,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  testId?: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      data-testid={testId}
      className={cn("rounded-lg border p-3 text-left transition", active ? "border-primary bg-primary/10" : "hover:border-primary/50", className)}
    >
      {children}
    </button>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
  feature,
  testId,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  feature?: string;
  testId?: string;
}) {
  return (
    <label className="flex items-center justify-between gap-3 text-sm">
      <span>
        <span className="flex items-center gap-2">
          {label} {feature && <LockedBadge feature={feature} />}
        </span>
        <span className="block text-xs text-muted-foreground">{hint}</span>
      </span>
      <Switch checked={checked} onCheckedChange={onChange} aria-label={label} data-testid={testId} />
    </label>
  );
}

export function NewClipForm({ initialUrl = "", initialMode = "auto" }: { initialUrl?: string; initialMode?: Mode }) {
  const router = useRouter();
  const gate = useGate();
  const [opts, setOpts] = useState<Options | null>(null);
  const [brandSaved, setBrandSaved] = useState(false);
  const [source, setSource] = useState<"link" | "upload" | "batch">("link");
  const [url, setUrl] = useState(initialUrl);
  const [batchText, setBatchText] = useState("");
  const [upload, setUpload] = useState<UploadInfo | null>(null);
  const [mode, setMode] = useState<Mode>(initialMode);
  const [aspect, setAspect] = useState<Aspect>("9:16");
  const [num, setNum] = useState(5);
  const [range, setRange] = useState<[number, number]>([20, 60]);
  const [contentType, setContentType] = useState("podcast");
  const [reframe, setReframe] = useState("face");
  const [language, setLanguage] = useState("auto");
  const [translateTo, setTranslateTo] = useState("none");
  const [visual, setVisual] = useState(false);
  const [hook, setHook] = useState(initialMode !== "captions");
  const [removeSilence, setRemoveSilence] = useState(false);
  const [removeFillers, setRemoveFillers] = useState(false);
  const [emphasis, setEmphasis] = useState(false);
  const [emphasisWords, setEmphasisWords] = useState("");
  const [progressBar, setProgressBar] = useState(false);
  const [useBrand, setUseBrand] = useState(false);
  const [musicMood, setMusicMood] = useState("none");
  const [musicVolume, setMusicVolume] = useState(0.2);
  const [style, setStyle] = useState<CaptionStyle>({ preset: "bold_pop" });
  const [quote, setQuote] = useState<Quote | null>(null);
  const [busy, setBusy] = useState(false);
  const { info, loading } = useLinkInfo(source === "link" ? url : "");

  useEffect(() => {
    api<Options>("/clipper/options").then((o) => {
      setOpts(o);
      setNum((n) => Math.min(n, o.max_clips));
    }).catch(() => {});
    api<{ saved: boolean; available: boolean; caption_preset: string | null }>("/brand")
      .then((b) => {
        setBrandSaved(b.saved);
        if (b.available && b.saved) {
          setUseBrand(true);
          if (b.caption_preset) setStyle({ preset: b.caption_preset as CaptionStyle["preset"] });
        }
      })
      .catch(() => {});
  }, []);

  const batchUrls = useMemo(() => [...new Set(batchText.split(/\s+/).map((s) => s.trim()).filter(isUrl))], [batchText]);
  const links = source === "batch" ? Math.max(1, batchUrls.length) : 1;
  const clipping = mode !== "captions";
  const jumpCuts = removeSilence || removeFillers;

  const pickMode = (m: Mode) => {
    setMode(m);
    setHook(m !== "captions");
  };
  const pickContent = (v: string) => {
    setContentType(v);
    if (v === "sports" || v === "gaming") {
      setReframe("action");
      if (gate.allowed("visual_analysis")) setVisual(true);
    }
  };
  const pickAspect = (a: Aspect) => (a !== "9:16" && !gate.allowed("output_formats") ? gate.explain("output_formats") : setAspect(a));
  const pickTranslate = (v: string) => (v !== "none" && !gate.allowed("translation") ? gate.explain("translation") : setTranslateTo(v));
  const pickSource = (v: string) => (v === "batch" && !gate.allowed("batch") ? gate.explain("batch") : setSource(v as typeof source));

  useEffect(() => {
    const q = new URLSearchParams({
      kind: "clip",
      mode: mode === "captions" ? "captions" : "clips",
      num_clips: String(num),
      visual_analysis: String(clipping && visual),
      translate: translateTo !== "none" ? "1" : "0",
      jump_cuts: String(jumpCuts),
      links: String(links),
    });
    const t = setTimeout(() => api<Quote>(`/tokens/quote?${q}`).then(setQuote).catch(() => setQuote(null)), 250);
    return () => clearTimeout(t);
  }, [mode, num, visual, clipping, translateTo, jumpCuts, links]);

  const ready = source === "link" ? isUrl(url) && !info?.too_long : source === "upload" ? !!upload : batchUrls.length > 0;

  const options = () => ({
    mode,
    aspect,
    num_clips: num,
    min_len: range[0],
    max_len: range[1],
    content_type: contentType,
    reframe,
    caption_style: style,
    language,
    translate_to: translateTo === "none" ? null : translateTo,
    visual_analysis: clipping && visual,
    hook_overlay: hook,
    remove_silence: removeSilence,
    remove_fillers: removeFillers,
    keyword_emphasis: emphasis,
    emphasis_words: emphasis ? emphasisWords.split(/[,\n]+/).map((s) => s.trim()).filter(Boolean) : [],
    progress_bar: progressBar,
    use_brand: useBrand,
    music_mood: musicMood,
    music_volume: musicVolume,
  });

  /** Apply a template, skipping anything the plan doesn't include. */
  const applyTemplate = (t: Record<string, unknown>) => {
    const locked: string[] = [];
    const ok = (feature: string, on: boolean) => {
      if (on && !gate.allowed(feature)) {
        locked.push(feature);
        return false;
      }
      return true;
    };
    if (t.mode) pickMode(t.mode as Mode);
    if (t.aspect && ok("output_formats", t.aspect !== "9:16")) setAspect(t.aspect as Aspect);
    if (typeof t.num_clips === "number") setNum(Math.min(t.num_clips, opts?.max_clips ?? 5));
    if (typeof t.min_len === "number" && typeof t.max_len === "number") setRange([t.min_len, t.max_len]);
    if (t.content_type) setContentType(String(t.content_type));
    if (t.reframe) setReframe(String(t.reframe));
    if (t.caption_style) setStyle(t.caption_style as CaptionStyle);
    if (t.language) setLanguage(String(t.language ?? "auto"));
    if ("hook_overlay" in t) setHook(Boolean(t.hook_overlay));
    if ("progress_bar" in t) setProgressBar(Boolean(t.progress_bar));
    if (t.music_mood) setMusicMood(String(t.music_mood));
    if (ok("visual_analysis", Boolean(t.visual_analysis))) setVisual(Boolean(t.visual_analysis));
    if (ok("translation", Boolean(t.translate_to))) setTranslateTo(t.translate_to ? String(t.translate_to) : "none");
    if (ok("filler_removal", Boolean(t.remove_silence || t.remove_fillers))) {
      setRemoveSilence(Boolean(t.remove_silence));
      setRemoveFillers(Boolean(t.remove_fillers));
    }
    if (ok("keyword_emphasis", Boolean(t.keyword_emphasis))) setEmphasis(Boolean(t.keyword_emphasis));
    if (locked.length) gate.explain(locked[0]);
  };

  const submit = async () => {
    setBusy(true);
    try {
      if (source === "batch") {
        const r = await api<{ created: { project_id: string }[]; error: { url: string; detail: string } | null }>("/clipper/batch", {
          method: "POST",
          json: { urls: batchUrls, options: options() },
        });
        if (r.created.length) toast.success(`Started ${r.created.length} video${r.created.length > 1 ? "s" : ""}`);
        if (r.error) toast.error(`Stopped at ${r.error.url}: ${r.error.detail}`);
        router.push("/clipper");
        return;
      }
      const r = await api<{ project_id: string }>("/clipper/projects", {
        method: "POST",
        json: {
          ...(source === "link" ? { url: url.trim() } : { upload_id: upload!.id, title: upload!.filename.replace(/\.[^.]+$/, "") }),
          ...options(),
        },
      });
      router.push(href(`/clipper/${r.project_id}`));
    } catch (e) {
      toast.error((e as Error).message);
      setBusy(false);
    }
  };

  const cta =
    source === "batch"
      ? `Start ${batchUrls.length || ""} video${batchUrls.length === 1 ? "" : "s"}`
      : mode === "captions"
        ? "Caption my video"
        : mode === "auto"
          ? "Make it"
          : `Make ${num} clip${num > 1 ? "s" : ""}`;

  return (
    <div className="grid max-w-4xl gap-6">
      <TemplateBar kind="clip" onApply={applyTemplate} current={() => options()} />
      <Card>
        <CardHeader>
          <CardTitle>1. Your video</CardTitle>
          <CardDescription>
            Paste a link from YouTube, TikTok, Instagram, X, Facebook, Vimeo, Twitch, Reddit and more, or upload the file. Uploading always
            works, even when a site blocks downloads.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs value={source} onValueChange={pickSource}>
            <TabsList className="mb-4">
              <TabsTrigger value="link">
                <Link2 className="mr-1.5 size-4" /> Link
              </TabsTrigger>
              <TabsTrigger value="upload">
                <Upload className="mr-1.5 size-4" /> Upload
              </TabsTrigger>
              <TabsTrigger value="batch" data-testid="batch-tab">
                <Layers className="mr-1.5 size-4" /> Batch <LockedBadge feature="batch" className="ml-1.5" />
              </TabsTrigger>
            </TabsList>
            <TabsContent value="link" className="grid gap-3">
              <Input placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} aria-label="Video link" autoFocus />
              <LinkPreview info={info} loading={loading} />
              {info?.suggested_mode && mode === "auto" && (
                <p className="text-xs text-muted-foreground" data-testid="auto-hint">
                  {info.suggested_mode === "captions"
                    ? "Short video: Auto will caption the whole thing (you pay the captions price)."
                    : "Long video: Auto will find the best clips."}
                </p>
              )}
            </TabsContent>
            <TabsContent value="upload">
              <UploadDropzone purpose="source" onComplete={setUpload} />
              {upload && <p className="mt-2 text-sm text-success">Ready: {upload.filename}</p>}
            </TabsContent>
            <TabsContent value="batch" className="grid gap-2">
              <Textarea
                rows={5}
                value={batchText}
                onChange={(e) => setBatchText(e.target.value)}
                placeholder={"One link per line\nhttps://www.youtube.com/watch?v=…\nhttps://www.tiktok.com/@…/video/…"}
                aria-label="Links, one per line"
              />
              <p className="text-xs text-muted-foreground">
                {batchUrls.length} link{batchUrls.length === 1 ? "" : "s"} · up to {opts?.max_batch ?? 1} at once on your plan. Each becomes its own
                project with the settings below; they run one after another.
              </p>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>2. What to make</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-6">
          <div className="grid gap-2 sm:grid-cols-3">
            {MODES.map((m) => (
              <Choice key={m.id} active={mode === m.id} onClick={() => pickMode(m.id)} testId={`mode-${m.id}`}>
                <p className="flex items-center gap-2 text-sm font-medium">
                  <m.icon className="size-4 text-primary" /> {m.label}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">{m.hint}</p>
              </Choice>
            ))}
          </div>
          <div>
            <p className="mb-2 flex items-center gap-2 text-sm font-medium">
              Format <LockedBadge feature="output_formats" />
            </p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {(opts?.aspects ?? [{ id: "9:16" as Aspect, label: "Vertical 9:16", hint: "TikTok, Reels, Shorts", locked: false }]).map((a) => (
                <Choice key={a.id} active={aspect === a.id} onClick={() => pickAspect(a.id)} testId={`aspect-${a.id}`} className={cn(a.locked && "opacity-70")}>
                  <div className="flex items-center gap-3">
                    <span className={cn("shrink-0 rounded-sm border-2 border-current", ASPECT_BOX[a.id], aspect === a.id ? "text-primary" : "text-muted-foreground")} />
                    <span>
                      <span className="block text-sm font-medium">{a.label}</span>
                      <span className="block text-xs text-muted-foreground">{a.hint}</span>
                    </span>
                  </div>
                </Choice>
              ))}
            </div>
          </div>
          {clipping && (
            <>
              <div className="grid gap-2 sm:grid-cols-4">
                {CONTENT.map((c) => (
                  <Choice key={c.value} active={contentType === c.value} onClick={() => pickContent(c.value)}>
                    <p className="text-sm font-medium">{c.label}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{c.hint}</p>
                  </Choice>
                ))}
              </div>
              <div className="grid gap-6 sm:grid-cols-2">
                <Field label={`Number of clips: ${num}`} hint={`Your plan makes up to ${opts?.max_clips ?? 5} per video`}>
                  <Slider min={1} max={opts?.max_clips ?? 5} step={1} value={[num]} onValueChange={([v]) => setNum(v)} aria-label="Number of clips" />
                </Field>
                <Field label={`Clip length: ${range[0]}–${range[1]} s`}>
                  <Slider min={15} max={180} step={5} value={range} minStepsBetweenThumbs={1} onValueChange={(v) => setRange([v[0], v[1]])} />
                </Field>
              </div>
              <Toggle
                label="Visual analysis"
                hint="The AI also watches the video (best for sports and gaming)"
                checked={visual}
                onChange={gate.guard("visual_analysis", setVisual)}
                feature="visual_analysis"
              />
            </>
          )}
          {mode === "captions" && (
            <p className="text-xs text-muted-foreground">Captions mode works on videos up to {opts?.captions_max_minutes ?? 15} minutes.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>3. Language & polish</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Spoken language">
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
            <Field label={<span className="flex items-center gap-2">Captions in <LockedBadge feature="translation" /></span>}>
              <Select
                value={translateTo}
                onValueChange={pickTranslate}
                aria-label="Translate captions to"
                options={[{ value: "none", label: "Same as spoken" }, ...(opts?.languages ?? []).map((l) => ({ value: l.code, label: l.name }))]}
              />
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Toggle label="Remove silences" hint="Cut long pauses for tighter pacing" checked={removeSilence} onChange={gate.guard("filler_removal", setRemoveSilence)} feature="filler_removal" testId="remove-silence" />
            <Toggle label="Remove filler words" hint={'Cut "um", "uh", "erm"…'} checked={removeFillers} onChange={gate.guard("filler_removal", setRemoveFillers)} feature="filler_removal" />
            <Toggle label="Keyword emphasis" hint="Highlight the words that matter" checked={emphasis} onChange={gate.guard("keyword_emphasis", setEmphasis)} feature="keyword_emphasis" />
            <Toggle label="Hook text" hint="Big text for the first 3 seconds" checked={hook} onChange={setHook} />
            <Toggle label="Progress bar" hint="A thin bar that fills as the video plays" checked={progressBar} onChange={setProgressBar} />
            <Toggle label="My brand kit" hint={brandSaved ? "Your logo and @handle on every video" : "Add your logo first in Account → Brand kit"} checked={useBrand} onChange={gate.guard("brand_kit", (v: boolean) => (v && !brandSaved ? toast.message("Set up your brand kit first", { action: { label: "Open", onClick: () => router.push("/account/brand") } }) : setUseBrand(v)))} feature="brand_kit" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Background music" hint="From the music library, automatically quieter while people talk">
              <Select value={musicMood} onValueChange={setMusicMood} aria-label="Background music" options={MUSIC_MOODS} />
            </Field>
            {musicMood !== "none" && (
              <Field label={`Music volume (${Math.round(musicVolume * 100)}%)`}>
                <Slider min={0.05} max={0.6} step={0.05} value={[musicVolume]} onValueChange={([v]) => setMusicVolume(v)} aria-label="Music volume" />
              </Field>
            )}
          </div>
          {emphasis && (
            <Field label="Always highlight these words (optional)">
              <Input value={emphasisWords} onChange={(e) => setEmphasisWords(e.target.value)} placeholder="free, secret, 10x" aria-label="Words to highlight" />
            </Field>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>4. Framing</CardTitle>
          <CardDescription>How the picture is fitted into the {aspect} frame.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2 sm:grid-cols-5">
          {REFRAME.map((r) => (
            <Choice key={r.value} active={reframe === r.value} onClick={() => setReframe(r.value)} testId={`reframe-${r.value}`}>
              <p className="text-sm font-medium">{r.label}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">{r.hint}</p>
            </Choice>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>5. Caption style</CardTitle>
        </CardHeader>
        <CardContent>
          <CaptionStylePicker value={style} onChange={setStyle} hook={hook ? "You won't believe this" : null} />
        </CardContent>
      </Card>

      <div className="sticky bottom-20 z-10 flex flex-wrap items-center justify-end gap-3 md:bottom-4">
        {quote && (
          <span className="flex items-center gap-1.5 rounded-full border bg-card/95 px-3 py-1.5 text-sm shadow backdrop-blur" data-testid="quote">
            <Coins className="size-4 text-primary" />
            {quote.unlimited ? (
              "Free for your team"
            ) : (
              <>
                {quote.tokens.toLocaleString()} tokens
                {mode === "auto" && <span className="text-muted-foreground">(max)</span>}
                {!quote.enough && (
                  <Link href="/account/tokens" className="ml-1 text-destructive underline">
                    you have {quote.balance.toLocaleString()}
                  </Link>
                )}
              </>
            )}
          </span>
        )}
        <Button size="lg" onClick={submit} disabled={!ready || busy || (quote ? !quote.enough : false)} className="shadow-xl" data-testid="create-clips">
          <Sparkles /> {busy ? "Starting…" : cta}
        </Button>
      </div>
    </div>
  );
}
