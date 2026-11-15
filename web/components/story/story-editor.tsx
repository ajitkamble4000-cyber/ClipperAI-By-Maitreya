"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Check, Cloud, Loader2, RefreshCw, Trash2, Zap } from "lucide-react";
import { toast } from "sonner";
import { JobProgress } from "@/components/jobs/job-progress";
import { useMe } from "@/components/shell/member-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SaveStateContext, useSaveIndicator } from "@/hooks/use-autosave";
import { useProjectJobs } from "@/hooks/use-job";
import { usePresence } from "@/hooks/use-presence";
import { useProjectRows } from "@/hooks/use-rows";
import { api } from "@/lib/api";
import { GENRES, LANGUAGES, estimateSeconds } from "@/lib/story";
import { supabaseBrowser } from "@/lib/supabase/client";
import { realtimeAuth } from "@/lib/supabase/realtime";
import type { Scene } from "./scene-card";
import { StoryMeta, type Story } from "./story-meta";
import { Storyboard } from "./storyboard";
import { storyStepTabs } from "./steps-registry";

const AI_KINDS = new Set(["story_script", "story_scene_ai"]);

function useStory(projectId: string) {
  const [story, setStory] = useState<Story | null | undefined>(undefined);
  useEffect(() => {
    const sb = supabaseBrowser();
    let ch: ReturnType<typeof sb.channel> | null = null;
    const load = () => sb.from("stories").select("*").eq("project_id", projectId).maybeSingle().then(({ data }) => setStory(data as Story | null));
    load();
    realtimeAuth(sb).then(() => {
      ch = sb
        .channel(`story-${projectId}`)
        .on("postgres_changes", { event: "UPDATE", schema: "public", table: "stories", filter: `project_id=eq.${projectId}` }, (p) =>
          setStory(p.new as Story),
        )
        .subscribe((s) => s === "SUBSCRIBED" && load());
    });
    return () => {
      if (ch) sb.removeChannel(ch);
    };
  }, [projectId]);
  return story;
}

export function StoryEditor({ projectId }: { projectId: string }) {
  const me = useMe();
  const router = useRouter();
  const story = useStory(projectId);
  const { rows: scenes, setRows: setScenes } = useProjectRows<Scene>("scenes", projectId);
  const jobs = useProjectJobs(projectId);
  const saveInd = useSaveIndicator();
  const viewers = usePresence(projectId, { user_id: me.user_id, name: me.display_name ?? me.email.split("@")[0] });
  const activeAi = useMemo(() => jobs.find((j) => AI_KINDS.has(j.kind) && (j.status === "queued" || j.status === "running")), [jobs]);
  const lastAi = useMemo(() => jobs.find((j) => AI_KINDS.has(j.kind)), [jobs]);
  const [tab, setTab] = useState("script");

  const total = (scenes ?? []).reduce((a, s) => a + estimateSeconds(s.narration), 0);

  const ai = async (path: string, msg: string) => {
    try {
      await api(path, { method: "POST" });
      toast.message(msg);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const remove = async () => {
    if (!confirm("Delete this story?")) return;
    await api(`/projects/${projectId}`, { method: "DELETE" }).then(() => router.replace("/story")).catch((e) => toast.error(e.message));
  };

  if (story === undefined) return <Skeleton className="h-60" />;
  if (story === null) return <p className="text-muted-foreground">Story not found.</p>;

  return (
    <SaveStateContext.Provider value={saveInd.report}>
      <div className="grid gap-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <Link href="/story" className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
              <ArrowLeft className="size-4" /> Story Studio
            </Link>
            <h1 className="truncate text-2xl font-semibold tracking-tight">{story.title || story.idea.slice(0, 80)}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="secondary">{GENRES[story.genre]?.label ?? story.genre}</Badge>
              <Badge variant="secondary">{story.length_s}s target</Badge>
              <Badge variant="secondary">{LANGUAGES[story.language]?.label}</Badge>
              <span data-testid="save-state" className="inline-flex items-center gap-1">
                {saveInd.state === "saving" ? (
                  <><Loader2 className="size-3 animate-spin" /> Saving…</>
                ) : saveInd.state === "saved" ? (
                  <><Check className="size-3 text-success" /> Saved</>
                ) : saveInd.state === "error" ? (
                  <span className="text-destructive">Not saved</span>
                ) : (
                  <><Cloud className="size-3" /> Autosave on</>
                )}
              </span>
              {viewers.length > 0 && (
                <span className="inline-flex items-center gap-1" data-testid="presence">
                  · Also editing: {viewers.map((v) => v.name).join(", ")}
                </span>
              )}
            </div>
          </div>
          {(me.role === "admin" || me.user_id) && (
            <Button variant="ghost" size="icon" onClick={remove} aria-label="Delete story">
              <Trash2 />
            </Button>
          )}
        </div>

        {activeAi && <JobProgress job={activeAi} compact />}
        {!activeAi && lastAi?.status === "failed" && <JobProgress job={lastAi} />}

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="script">1. Script</TabsTrigger>
            {storyStepTabs.map((t) => (
              <TabsTrigger key={t.id} value={t.id} disabled={!scenes?.length}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="script" className="mt-5 grid gap-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">
                {scenes?.length ?? 0} scenes · ~{total.toFixed(0)} s of narration (target {story.length_s} s)
              </p>
              <div className="flex gap-2">
                <Button variant="secondary" disabled={!!activeAi || !scenes?.length} onClick={() => ai(`/story/${projectId}/hook`, "Strengthening the hook…")}>
                  <Zap /> Make the hook stronger
                </Button>
                <Button
                  variant="outline"
                  disabled={!!activeAi}
                  onClick={() => (!scenes?.length || confirm("Replace the whole storyboard with a new script?")) && ai(`/story/${projectId}/script`, "Writing a new script…")}
                >
                  <RefreshCw /> {scenes?.length ? "Regenerate script" : "Write script"}
                </Button>
              </div>
            </div>
            {scenes && scenes.length > 0 && <StoryMeta story={story} />}
            {scenes === null ? (
              <Skeleton className="h-40" />
            ) : scenes.length === 0 && !activeAi ? (
              <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">No scenes yet. Write the script to start.</p>
            ) : (
              <Storyboard projectId={projectId} scenes={scenes} setScenes={setScenes} aiBusy={!!activeAi} />
            )}
          </TabsContent>
          {storyStepTabs.map((t) => (
            <TabsContent key={t.id} value={t.id} className="mt-5">
              {scenes && <t.Component story={story} scenes={scenes} setScenes={setScenes} jobs={jobs} />}
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </SaveStateContext.Provider>
  );
}
