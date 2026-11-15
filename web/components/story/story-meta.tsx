"use client";

import { useEffect, useRef, useState } from "react";
import { Input, Textarea } from "@/components/ui/input";
import { useAutosave } from "@/hooks/use-autosave";

export interface Story {
  project_id: string;
  idea: string;
  input_mode: string;
  genre: string;
  visual_style: string;
  length_s: number;
  language: string;
  voice: string | null;
  speaking_style: string;
  voiceover_key: string | null;
  motion_mode: "standard" | "premium";
  music_track_id: string | null;
  music_auto: boolean;
  music_volume: number;
  sfx_enabled: boolean;
  caption_style: Record<string, unknown>;
  hook_overlay: boolean;
  title: string;
  description: string;
  hashtags: string[];
  hook_text: string;
  narration_key: string | null;
  alignment_key: string | null;
  render_key: string | null;
  thumb_key: string | null;
  covers?: { youtube?: string; vertical?: string; style?: "frame" | "ai" };
  ideas?: { titles?: string[]; hashtags?: string[]; description?: string };
  updated_at: string;
}

export function StoryMeta({ story }: { story: Story }) {
  const { save } = useAutosave("stories", { project_id: story.project_id });
  const projectSave = useAutosave("projects", { id: story.project_id });
  const [v, setV] = useState({ title: story.title, hook_text: story.hook_text, description: story.description, hashtags: story.hashtags.join(" ") });
  const focused = useRef<string | null>(null);
  useEffect(() => {
    setV((p) => ({
      title: focused.current === "title" ? p.title : story.title,
      hook_text: focused.current === "hook_text" ? p.hook_text : story.hook_text,
      description: focused.current === "description" ? p.description : story.description,
      hashtags: focused.current === "hashtags" ? p.hashtags : story.hashtags.join(" "),
    }));
  }, [story.title, story.hook_text, story.description, story.hashtags]);
  const f = (k: keyof typeof v) => ({
    value: v[k],
    onFocus: () => (focused.current = k),
    onBlur: () => (focused.current = null),
  });
  return (
    <div className="grid gap-3 rounded-xl border bg-card p-4 sm:grid-cols-2">
      <div className="grid gap-1.5">
        <label className="text-xs font-medium text-muted-foreground" htmlFor="story-title">Title ({v.title.length}/60)</label>
        <Input id="story-title" {...f("title")} onChange={(e) => { setV({ ...v, title: e.target.value }); save({ title: e.target.value }); projectSave.save({ title: e.target.value || "Untitled story" }); }} />
      </div>
      <div className="grid gap-1.5">
        <label className="text-xs font-medium text-muted-foreground" htmlFor="story-hook">Hook text (first 3 s)</label>
        <Input id="story-hook" {...f("hook_text")} onChange={(e) => { setV({ ...v, hook_text: e.target.value }); save({ hook_text: e.target.value }); }} />
      </div>
      <div className="grid gap-1.5">
        <label className="text-xs font-medium text-muted-foreground" htmlFor="story-desc">Description</label>
        <Textarea id="story-desc" rows={2} {...f("description")} onChange={(e) => { setV({ ...v, description: e.target.value }); save({ description: e.target.value }); }} />
      </div>
      <div className="grid gap-1.5">
        <label className="text-xs font-medium text-muted-foreground" htmlFor="story-tags">Hashtags</label>
        <Textarea
          id="story-tags"
          rows={2}
          {...f("hashtags")}
          onChange={(e) => {
            setV({ ...v, hashtags: e.target.value });
            save({ hashtags: e.target.value.split(/[\s,]+/).filter(Boolean).map((t) => (t.startsWith("#") ? t : `#${t}`)) });
          }}
        />
      </div>
    </div>
  );
}
