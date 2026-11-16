"use client";

import { ExtrasPanel } from "@/components/clipper/extras-panel";
import { RepurposePanel } from "@/components/projects/repurpose-panel";
import { useEffect, useState } from "react";
import { Clapperboard, Download } from "lucide-react";
import { toast } from "sonner";
import { CaptionStylePicker } from "@/components/captions/caption-style-picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { useAutosave } from "@/hooks/use-autosave";
import { api, signedUrl } from "@/lib/api";
import type { CaptionStyle } from "@/lib/presets";
import { GENRES } from "@/lib/story";
import { supabaseBrowser } from "@/lib/supabase/client";
import { premiumPanel } from "./premium-slot";
import { isActive, latestJob, StepJob, useSigned } from "./step-utils";
import type { StepProps } from "./steps-registry";

interface Track {
  id: string;
  name: string;
  mood: string;
}

export function RenderStep(props: StepProps) {
  const { story, scenes, jobs } = props;
  const pid = story.project_id;
  const { save } = useAutosave("stories", { project_id: pid }, 300);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [music, setMusic] = useState(story.music_auto ? "auto" : story.music_track_id ?? "none");
  const [volume, setVolume] = useState(Number(story.music_volume));
  const [sfx, setSfx] = useState(story.sfx_enabled);
  const [hook, setHook] = useState(story.hook_overlay);
  const [mode, setMode] = useState(story.motion_mode);
  const [style, setStyle] = useState<CaptionStyle>(
    (Object.keys(story.caption_style ?? {}).length ? story.caption_style : { preset: GENRES[story.genre]?.captions ?? "bold_pop" }) as unknown as CaptionStyle,
  );
  const job = latestJob(jobs, ["story_render"]);
  const video = useSigned(story.render_key);
  const poster = useSigned(story.thumb_key);
  const missingImages = scenes.filter((s) => !s.image_key && !s.video_key).length;
  const ready = !missingImages && !!story.narration_key;

  useEffect(() => {
    supabaseBrowser().from("music_tracks").select("id,name,mood").order("mood").then(({ data }) => setTracks((data as Track[]) ?? []));
  }, []);

  const render = async () => {
    try {
      await api(`/story/${pid}/render`, { method: "POST" });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const download = async () => {
    if (!story.render_key) return;
    window.location.href = await signedUrl(story.render_key, story.render_key.split("/").pop());
  };

  const Premium = premiumPanel.Component;

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_300px]">
      <div className="grid content-start gap-5">
        <Card>
          <CardHeader>
            <CardTitle>Motion</CardTitle>
            <CardDescription>Standard animates each image with smooth zoom/pan (free). Premium turns chosen scenes into AI video with Veo.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="flex gap-2">
              {(["standard", "premium"] as const).map((m) => (
                <Button key={m} variant={mode === m ? "default" : "outline"} size="sm" onClick={() => { setMode(m); save({ motion_mode: m }); }}>
                  {m === "standard" ? "Standard (Ken Burns)" : "Premium AI video"}
                </Button>
              ))}
            </div>
            {mode === "premium" && Premium && <Premium {...props} />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Sound</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field label="Music" hint={tracks.length ? undefined : "No tracks yet. An admin can add royalty-free music in Settings → Library."}>
              <Select
                value={music}
                onValueChange={(v) => {
                  setMusic(v);
                  save(v === "auto" ? { music_auto: true, music_track_id: null } : v === "none" ? { music_auto: false, music_track_id: null } : { music_auto: false, music_track_id: v });
                }}
                options={[
                  { value: "auto", label: `Auto (${GENRES[story.genre]?.music} mood)` },
                  { value: "none", label: "No music" },
                  ...tracks.map((t) => ({ value: t.id, label: `${t.name} · ${t.mood}` })),
                ]}
              />
            </Field>
            <Field label={`Music volume (${Math.round(volume * 100)}%)`} hint="Automatically ducked under the voice">
              <Slider min={0.05} max={0.6} step={0.05} value={[volume]} onValueChange={([v]) => { setVolume(v); save({ music_volume: v }); }} />
            </Field>
            <label className="flex items-center justify-between gap-3 text-sm">
              Sound effects at scene cuts <Switch checked={sfx} onCheckedChange={(v) => { setSfx(v); save({ sfx_enabled: v }); }} />
            </label>
            <label className="flex items-center justify-between gap-3 text-sm">
              Hook text for the first 3 s <Switch checked={hook} onCheckedChange={(v) => { setHook(v); save({ hook_overlay: v }); }} />
            </label>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Captions</CardTitle>
          </CardHeader>
          <CardContent>
            <CaptionStylePicker value={style} onChange={(s) => { setStyle(s); save({ caption_style: s }); }} hook={hook ? story.hook_text : null} compact />
          </CardContent>
        </Card>
      </div>
      <div className="grid content-start gap-4">
        <div className="aspect-[9/16] overflow-hidden rounded-xl border bg-black">
          {video ? (
            <video key={video} src={video} poster={poster ?? undefined} controls playsInline className="size-full" data-testid="story-video" />
          ) : (
            <div className="flex size-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground">
              <Clapperboard className="size-8" />
              {ready ? "Ready to render" : missingImages ? `${missingImages} scene${missingImages > 1 ? "s" : ""} still need images` : "Generate the voiceover first"}
            </div>
          )}
        </div>
        <StepJob job={job} />
        <Button size="lg" onClick={render} disabled={!ready || isActive(job)} data-testid="render">
          {story.render_key ? "Re-render" : "Render video"}
        </Button>
        {story.render_key && (
          <Button variant="secondary" onClick={download}>
            <Download /> Download MP4
          </Button>
        )}
        <p className="text-xs text-muted-foreground">Re-rendering reuses every image, voice and animated scene; only what changed is redone.</p>
        {story.render_key && <RepurposePanel projectId={story.project_id} title={story.title || "story"} />}
        {story.render_key && (
          <ExtrasPanel
            base={`/story/${story.project_id}`}
            covers={story.covers}
            ideas={story.ideas}
            onUseTitle={(t) => save({ title: t })}
            onUseHashtags={(h) => save({ hashtags: h })}
          />
        )}
      </div>
    </div>
  );
}
