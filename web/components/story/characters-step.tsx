"use client";

import { useState } from "react";
import { Lock, Plus, RefreshCw, Trash2, Unlock, Users } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { useAutosave } from "@/hooks/use-autosave";
import { useProjectRows } from "@/hooks/use-rows";
import { api } from "@/lib/api";
import { supabaseBrowser } from "@/lib/supabase/client";
import { isActive, latestJob, StepJob, useSigned } from "./step-utils";
import type { StepProps } from "./steps-registry";

interface Character {
  id: string;
  name: string;
  description: string;
  ref_key: string | null;
  locked: boolean;
}

function CharacterCard({ c, busy }: { c: Character; busy: boolean }) {
  const url = useSigned(c.ref_key);
  const { save } = useAutosave("characters", { id: c.id });
  const [desc, setDesc] = useState(c.description);
  const [name, setName] = useState(c.name);
  return (
    <div className="grid grid-cols-[96px_1fr] gap-3 rounded-xl border bg-card p-3" data-testid="character-card">
      <div className="aspect-[9/16] overflow-hidden rounded-lg bg-muted">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {url ? <img src={url} alt={c.name} className="size-full object-cover" /> : <Users className="m-auto mt-10 size-6 text-muted-foreground" />}
      </div>
      <div className="grid content-start gap-2">
        <Input value={name} disabled={c.locked} onChange={(e) => { setName(e.target.value); save({ name: e.target.value }); }} aria-label="Character name" />
        <Textarea rows={3} value={desc} disabled={c.locked} onChange={(e) => { setDesc(e.target.value); save({ description: e.target.value }); }} aria-label="Character description" />
        <div className="flex flex-wrap gap-1">
          <Button size="sm" variant="secondary" disabled={busy || c.locked} data-char-regen={c.id}>
            <RefreshCw /> {c.ref_key ? "Regenerate" : "Generate"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => supabaseBrowser().from("characters").update({ locked: !c.locked }).eq("id", c.id).then(({ error }) => error && toast.error(error.message))}
          >
            {c.locked ? <><Lock /> Locked</> : <><Unlock /> Lock</>}
          </Button>
          <Button size="icon" variant="ghost" aria-label={`Delete ${c.name}`} disabled={c.locked}
            onClick={() => supabaseBrowser().from("characters").delete().eq("id", c.id).then(({ error }) => error && toast.error(error.message))}>
            <Trash2 />
          </Button>
        </div>
      </div>
    </div>
  );
}

export function CharactersStep({ story, jobs }: StepProps) {
  const pid = story.project_id;
  const { rows, reload } = useProjectRows<Character>("characters", pid, "created_at");
  const job = latestJob(jobs, ["story_characters"]);
  const busy = isActive(job);
  const [name, setName] = useState("");

  const generate = async (ids?: string[]) => {
    try {
      await api(`/story/${pid}/characters`, { method: "POST", json: { character_ids: ids ?? null } });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const add = async () => {
    if (!name.trim()) return;
    await api(`/story/${pid}/characters/add`, { method: "POST", json: { name, description: "" } }).catch((e) => toast.error(e.message));
    setName("");
    reload();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Characters</CardTitle>
        <CardDescription>
          Recurring characters get a reference image that is passed into every scene image, so they look the same throughout. Lock a
          character to keep it when regenerating the script.
        </CardDescription>
      </CardHeader>
      <CardContent
        className="grid gap-4"
        onClick={(e) => {
          const id = (e.target as HTMLElement).closest("[data-char-regen]")?.getAttribute("data-char-regen");
          if (id) generate([id]);
        }}
      >
        <StepJob job={job} />
        {rows && rows.length === 0 && <p className="text-sm text-muted-foreground">No recurring characters in this story. That's fine for most explainers and facts.</p>}
        <div className="grid gap-3 md:grid-cols-2">{rows?.map((c) => <CharacterCard key={c.id} c={c} busy={busy} />)}</div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input placeholder="Add a character by name" value={name} onChange={(e) => setName(e.target.value)} />
          <Button variant="outline" onClick={add}>
            <Plus /> Add
          </Button>
          <Button onClick={() => generate()} disabled={busy || !rows?.some((c) => !c.ref_key && !c.locked)}>
            Generate missing references
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
