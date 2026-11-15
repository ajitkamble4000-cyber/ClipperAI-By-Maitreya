"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { GENRES, LANGUAGES, LENGTHS, SPEAKING_STYLES, VOICES } from "@/lib/story";
import { cn } from "@/lib/utils";
import { StyleThumb } from "./style-thumb";

export interface VisualStyle {
  id: string;
  name: string;
  example_key: string | null;
  builtin: boolean;
}

export function NewStoryForm() {
  const router = useRouter();
  const [mode, setMode] = useState<"idea" | "script">("idea");
  const [idea, setIdea] = useState("");
  const [genre, setGenre] = useState("what_if");
  const [styles, setStyles] = useState<VisualStyle[]>([]);
  const [visual, setVisual] = useState("realistic_3d");
  const [length, setLength] = useState(45);
  const [language, setLanguage] = useState("en");
  const [voice, setVoice] = useState(GENRES.what_if.voice);
  const [speaking, setSpeaking] = useState(GENRES.what_if.speaking_style);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ visual_styles: VisualStyle[] }>("/story/presets").then((r) => setStyles(r.visual_styles)).catch(() => {});
  }, []);

  const pickGenre = (g: string) => {
    setGenre(g);
    setVisual(GENRES[g].visual_style);
    setVoice(GENRES[g].voice);
    setSpeaking(GENRES[g].speaking_style);
  };

  const submit = async () => {
    setBusy(true);
    try {
      const r = await api<{ project_id: string }>("/story/projects", {
        method: "POST",
        json: { idea, input_mode: mode, genre, visual_style: visual, length_s: length, language, voice, speaking_style: speaking },
      });
      router.push(`/story/${r.project_id}`);
    } catch (e) {
      toast.error((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="grid max-w-4xl gap-6">
      <Card>
        <CardHeader>
          <CardTitle>1. Idea or script</CardTitle>
          <CardDescription>Nothing is generated except the script until you approve the storyboard.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <Tabs value={mode} onValueChange={(v) => setMode(v as "idea" | "script")}>
            <TabsList>
              <TabsTrigger value="idea">Idea</TabsTrigger>
              <TabsTrigger value="script">Paste my script</TabsTrigger>
            </TabsList>
          </Tabs>
          <Textarea
            rows={mode === "idea" ? 3 : 10}
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
            placeholder={mode === "idea" ? GENRES[genre].example : "Paste the narration. It will be split into scenes and given image prompts."}
            aria-label="Story idea"
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>2. Genre</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {Object.entries(GENRES).map(([id, g]) => (
            <button
              type="button"
              key={id}
              onClick={() => pickGenre(id)}
              className={cn("rounded-lg border p-3 text-left transition", genre === id ? "border-primary bg-primary/10" : "hover:border-primary/50")}
              data-testid={`genre-${id}`}
            >
              <p className="text-sm font-medium">{g.label}</p>
              <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">e.g. {g.example}</p>
            </button>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>3. Visual style</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-3 gap-3 sm:grid-cols-5">
          {styles.map((s) => (
            <button type="button" key={s.id} onClick={() => setVisual(s.id)} className="text-left">
              <StyleThumb style={s} active={visual === s.id} />
              <p className={cn("mt-1 text-xs", visual === s.id ? "text-primary" : "text-muted-foreground")}>{s.name}</p>
            </button>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>4. Length, language and voice</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <Field label="Length">
            <div className="flex gap-2">
              {LENGTHS.map((l) => (
                <Button key={l} type="button" variant={length === l ? "default" : "outline"} size="sm" onClick={() => setLength(l)}>
                  {l}s
                </Button>
              ))}
            </div>
          </Field>
          <Field label="Narration language">
            <Select value={language} onValueChange={setLanguage} options={Object.entries(LANGUAGES).map(([v, l]) => ({ value: v, label: l.label }))} />
          </Field>
          <Field label="Voice" hint="You can preview voices and upload your own recording in the Voice step.">
            <Select value={voice} onValueChange={setVoice} options={VOICES.map((v) => ({ value: v.name, label: `${v.name} · ${v.desc}` }))} />
          </Field>
          <Field label="Speaking style">
            <Select value={speaking} onValueChange={setSpeaking} options={Object.entries(SPEAKING_STYLES).map(([v, s]) => ({ value: v, label: s.label }))} />
          </Field>
        </CardContent>
      </Card>
      <div className="sticky bottom-20 z-10 flex justify-end md:bottom-4">
        <Button size="lg" className="shadow-xl" disabled={idea.trim().length < 3 || busy} onClick={submit} data-testid="write-script">
          {busy ? "Starting…" : "Write the script"}
        </Button>
      </div>
    </div>
  );
}
