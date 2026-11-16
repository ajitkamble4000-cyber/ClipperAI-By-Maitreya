"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Scissors, Search, Sparkles } from "lucide-react";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { supabaseBrowser } from "@/lib/supabase/client";
import { realtimeAuth } from "@/lib/supabase/realtime";
import { timeAgo } from "@/lib/utils";
import { ProjectThumb } from "./project-thumb";
import { TranscriptSearch } from "./transcript-search";
import { href } from "@/lib/routes";

interface Row {
  id: string;
  type: "clip" | "story";
  title: string;
  status: string;
  created_at: string;
  created_by: string | null;
  thumbnail_key: string | null;
}

const STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "secondary" | "default"> = {
  ready: "success",
  rendered: "success",
  processing: "warning",
  rendering: "warning",
  failed: "destructive",
  render_failed: "destructive",
  draft: "secondary",
};

export function LibraryView({ fixedType }: { fixedType?: "clip" | "story" } = {}) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [members, setMembers] = useState<Record<string, string>>({});
  const [q, setQ] = useState("");
  const [type, setType] = useState<string>(fixedType ?? "all");
  const [creator, setCreator] = useState("all");
  const [status, setStatus] = useState("all");
  const [shared, setShared] = useState<Record<string, { role: string; owner_name: string }>>({});

  useEffect(() => {
    const sb = supabaseBrowser();
    const load = () =>
      sb
        .from("projects")
        .select("id,type,title,status,created_at,created_by,thumbnail_key")
        .order("created_at", { ascending: false })
        .limit(500)
        .then(({ data }) => setRows((data as Row[]) ?? []));
    load();
    sb.from("members")
      .select("user_id,email,display_name")
      .then(({ data }) =>
        setMembers(Object.fromEntries((data ?? []).map((m) => [m.user_id, m.display_name || m.email.split("@")[0]]))),
      );
    api<{ id: string; role: string; owner_name: string }[]>("/shared-with-me")
      .then((list) => setShared(Object.fromEntries(list.map((p) => [p.id, { role: p.role, owner_name: p.owner_name }]))))
      .catch(() => {});
    let ch: ReturnType<typeof sb.channel> | null = null;
    realtimeAuth(sb).then(() => {
      ch = sb.channel("library").on("postgres_changes", { event: "*", schema: "public", table: "projects" }, load).subscribe();
    });
    return () => {
      if (ch) sb.removeChannel(ch);
    };
  }, []);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (rows ?? []).filter(
      (r) =>
        (type === "all" || r.type === type) &&
        (creator === "all" || (creator === "shared" ? !!shared[r.id] : r.created_by === creator)) &&
        (status === "all" || r.status === status) &&
        (!needle || r.title.toLowerCase().includes(needle)),
    );
  }, [rows, q, type, creator, status, shared]);

  const statuses = useMemo(() => [...new Set((rows ?? []).map((r) => r.status))], [rows]);

  return (
    <>
      <PageHeader
        title={fixedType === "clip" ? "Clipper" : fixedType === "story" ? "Story Studio" : "Library"}
        description={
          fixedType === "clip"
            ? "Turn long videos into vertical Shorts with animated captions."
            : fixedType === "story"
              ? "Original animated stories from just an idea."
              : "Every project in the workspace."
        }
        actions={
          <div className="flex gap-2">
            <Button asChild variant="secondary">
              <Link href="/clipper/new">
                <Scissors /> New clips
              </Link>
            </Button>
            <Button asChild>
              <Link href="/story/new">
                <Sparkles /> New story
              </Link>
            </Button>
          </div>
        }
      />
      {!fixedType && (
        <div className="mb-4">
          <TranscriptSearch />
        </div>
      )}
      <div className="mb-5 grid gap-2 sm:grid-cols-[1fr_repeat(3,minmax(0,160px))]">
        <div className="relative">
          <Search className="absolute left-3 top-3 size-4 text-muted-foreground" />
          <Input placeholder="Search titles" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" aria-label="Search titles" />
        </div>
        {!fixedType && <Select
          value={type}
          onValueChange={setType}
          options={[
            { value: "all", label: "All types" },
            { value: "clip", label: "Clips" },
            { value: "story", label: "Stories" },
          ]}
        />}
        <Select
          value={creator}
          onValueChange={setCreator}
          aria-label="Made by"
          options={[
            { value: "all", label: "Everyone" },
            ...(Object.keys(shared).length ? [{ value: "shared", label: "Shared with me" }] : []),
            ...Object.entries(members).map(([value, label]) => ({ value, label })),
          ]}
        />
        <Select
          value={status}
          onValueChange={setStatus}
          options={[{ value: "all", label: "Any status" }, ...statuses.map((s) => ({ value: s, label: s.replace("_", " ") }))]}
        />
      </div>
      {rows === null ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[9/16]" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed p-12 text-center text-sm text-muted-foreground">
          {rows.length === 0 ? "No projects yet. Start with New clips or New story." : "Nothing matches these filters."}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5" data-testid="library-grid">
          {filtered.map((r) => (
            <Link key={r.id} href={href(r.type === "clip" ? `/clipper/${r.id}` : `/story/${r.id}`)} className="group">
              <ProjectThumb thumbKey={r.thumbnail_key} type={r.type} />
              <div className="mt-2 flex items-start justify-between gap-2">
                <p className="line-clamp-2 text-sm font-medium group-hover:text-primary">{r.title}</p>
                <Badge variant={STATUS_VARIANT[r.status] ?? "secondary"} className="shrink-0 capitalize">
                  {r.status.replace("_", " ")}
                </Badge>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {r.type === "clip" ? "Clips" : "Story"} · {members[r.created_by ?? ""] ?? shared[r.id]?.owner_name?.split("@")[0] ?? "Unknown"} ·{" "}
                {timeAgo(r.created_at)}
              </p>
              {shared[r.id] && (
                <Badge variant="secondary" className="mt-1" data-testid="shared-badge">
                  Shared with you · {shared[r.id].role === "editor" ? "can edit" : "view only"}
                </Badge>
              )}
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
