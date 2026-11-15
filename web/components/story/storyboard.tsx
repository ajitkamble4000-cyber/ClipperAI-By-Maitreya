"use client";

import { Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { supabaseBrowser } from "@/lib/supabase/client";
import { SceneCard, type Scene } from "./scene-card";

export function Storyboard({
  projectId,
  scenes,
  setScenes,
  aiBusy,
  renderExtra,
}: {
  projectId: string;
  scenes: Scene[];
  setScenes: (fn: (s: Scene[] | null) => Scene[] | null) => void;
  aiBusy: boolean;
  renderExtra?: (s: Scene) => React.ReactNode;
}) {
  const sorted = [...scenes].sort((a, b) => a.idx - b.idx);

  const reindex = async (list: Scene[]) => {
    setScenes(() => list.map((s, i) => ({ ...s, idx: i })));
    const sb = supabaseBrowser();
    const results = await Promise.all(list.map((s, i) => (s.idx === i ? null : sb.from("scenes").update({ idx: i }).eq("id", s.id))));
    if (results.some((r) => r?.error)) toast.error("Could not save the new order");
  };

  const move = (i: number, dir: -1 | 1) => {
    const list = sorted.slice();
    const [s] = list.splice(i, 1);
    list.splice(i + dir, 0, s);
    reindex(list);
  };

  const remove = async (s: Scene) => {
    if (sorted.length <= 1) return toast.error("A story needs at least one scene");
    const { error } = await supabaseBrowser().from("scenes").delete().eq("id", s.id);
    if (error) return toast.error(error.message);
    reindex(sorted.filter((x) => x.id !== s.id));
  };

  const add = async (at: number) => {
    const sb = supabaseBrowser();
    const list = sorted.slice();
    // shift following scenes, then insert
    await Promise.all(list.slice(at).map((s) => sb.from("scenes").update({ idx: s.idx + 1 }).eq("id", s.id)));
    const { data, error } = await sb
      .from("scenes")
      .insert({ project_id: projectId, idx: at, narration: "", image_prompt: "", camera_motion: "zoom-in", duration_estimate: 3 })
      .select("*")
      .single();
    if (error) return toast.error(error.message);
    list.splice(at, 0, data as Scene);
    setScenes(() => list.map((s, i) => ({ ...s, idx: i })));
  };

  return (
    <div className="grid gap-3" data-testid="storyboard">
      {sorted.map((s, i) => (
        <div key={s.id} className="grid gap-3">
          <SceneCard scene={s} position={i} total={sorted.length} onMove={(d) => move(i, d)} onDelete={() => remove(s)} aiBusy={aiBusy}>
            {renderExtra?.(s)}
          </SceneCard>
        </div>
      ))}
      <Button variant="outline" onClick={() => add(sorted.length)} className="border-dashed" data-testid="add-scene">
        <Plus /> Add scene
      </Button>
    </div>
  );
}
