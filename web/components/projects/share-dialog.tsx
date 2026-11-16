"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, LogOut, Trash2, UserPlus, Users } from "lucide-react";
import { toast } from "sonner";
import { LockedBadge, useGate } from "@/components/plan/locked";
import { useMe } from "@/components/shell/member-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";

type Role = "viewer" | "editor";
interface Person {
  user_id: string;
  email: string;
  display_name: string | null;
  role?: Role;
}
export interface ProjectAccess {
  owner: Person | null;
  members: Person[];
  /** owner | admin | team | viewer | editor */
  my_access: string | null;
}

const ROLE_OPTIONS = [
  { value: "viewer", label: "Can view" },
  { value: "editor", label: "Can edit" },
];

/** Who can see this project, and what the current user may do with it. */
export function useProjectAccess(projectId: string) {
  const [access, setAccess] = useState<ProjectAccess | null>(null);
  const reload = useCallback(
    () =>
      api<ProjectAccess>(`/projects/${projectId}/members`)
        .then(setAccess)
        .catch(() => setAccess(null)),
    [projectId],
  );
  useEffect(() => {
    reload();
  }, [reload]);
  return { access, reload };
}

/** A notice for people a project was shared with as viewers. */
export function ViewOnlyBanner({ access }: { access: ProjectAccess | null }) {
  if (access?.my_access !== "viewer") return null;
  const owner =
    access.owner?.display_name || access.owner?.email || "its owner";
  return (
    <div
      className="flex items-center gap-2 rounded-xl border bg-muted/40 p-3 text-sm"
      data-testid="view-only"
    >
      <Eye className="size-4 shrink-0 text-muted-foreground" />
      <span>
        <b>{owner}</b> shared this with you to view. You can watch and download,
        but not change it.
      </span>
    </div>
  );
}

function name(p: Person) {
  return p.display_name || p.email.split("@")[0];
}

/** "Share" for the owner (invite, change role, remove); "Shared with you" + Leave for invitees. */
export function ShareButton({
  projectId,
  access,
  reload,
}: {
  projectId: string;
  access: ProjectAccess | null;
  reload: () => void;
}) {
  const me = useMe();
  const router = useRouter();
  const { allowed, explain } = useGate();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [busy, setBusy] = useState(false);

  if (!access) return null;
  const manager = access.my_access === "owner" || access.my_access === "admin";
  const invitee =
    access.my_access === "viewer" || access.my_access === "editor";
  if (!manager && !invitee) return null;

  const invite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!allowed("collaboration")) return explain("collaboration");
    setBusy(true);
    try {
      const r = await api<{ email: string }>(`/projects/${projectId}/members`, {
        method: "POST",
        json: { email: email.trim(), role },
      });
      toast.success(`Shared with ${r.email}`);
      setEmail("");
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const change = async (p: Person, r: string) => {
    try {
      await api(`/projects/${projectId}/members/${p.user_id}`, {
        method: "PATCH",
        json: { role: r },
      });
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };
  const remove = async (p: Person) => {
    const leaving = p.user_id === me.user_id;
    if (
      leaving &&
      !confirm(
        "Leave this project? You'll lose access until the owner shares it again.",
      )
    )
      return;
    try {
      await api(`/projects/${projectId}/members/${p.user_id}`, {
        method: "DELETE",
      });
      if (leaving) {
        toast.success("You left the project");
        router.replace("/library");
      } else {
        toast.success(`Removed ${name(p)}`);
        reload();
      }
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  return (
    <>
      <Button
        variant="outline"
        onClick={() => setOpen(true)}
        data-testid="share"
      >
        <Users />
        {invitee
          ? access.my_access === "editor"
            ? "Shared · can edit"
            : "Shared · view only"
          : `Share${access.members.length ? ` (${access.members.length})` : ""}`}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        {/* one column pinned to the dialog width so long emails truncate instead of widening it */}
        <DialogContent className="grid-cols-[minmax(0,1fr)]">
          <DialogTitle>
            {manager ? "Share this project" : "Shared with you"}
          </DialogTitle>
          <DialogDescription>
            {manager
              ? "Invite people who already have an account. Viewers can watch and download; editors can change and re-render (using their own tokens)."
              : "These are the people who can open this project."}
          </DialogDescription>

          {manager && (
            <form
              onSubmit={invite}
              className="grid min-w-0 gap-2 sm:grid-cols-[minmax(0,1fr)_130px_auto]"
            >
              <Input
                type="email"
                required
                placeholder="name@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-label="Email to share with"
              />
              <Select
                value={role}
                onValueChange={(v) => setRole(v as Role)}
                options={ROLE_OPTIONS}
                aria-label="Access"
              />
              <Button
                type="submit"
                disabled={busy || !email.trim()}
                data-testid="share-invite"
              >
                <UserPlus /> Invite <LockedBadge feature="collaboration" />
              </Button>
            </form>
          )}

          <ul className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-1.5" data-testid="share-list">
            {access.owner && (
              <li className="flex min-w-0 items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm">
                <span className="min-w-0">
                  <span className="block truncate">{name(access.owner)}</span>
                  <span className="block truncate text-xs text-muted-foreground">{access.owner.email}</span>
                </span>
                <Badge variant="secondary">Owner</Badge>
              </li>
            )}
            {access.members.map((p) => (
              <li
                key={p.user_id}
                className="flex min-w-0 items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm"
                data-testid="share-person"
              >
                <span className="min-w-0">
                  <span className="block truncate">
                    {name(p)}
                    {p.user_id === me.user_id && <span className="text-muted-foreground"> (you)</span>}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">{p.email}</span>
                </span>
                <span className="flex shrink-0 items-center gap-1">
                  {manager ? (
                    <Select
                      value={p.role ?? "viewer"}
                      onValueChange={(v) => change(p, v)}
                      options={ROLE_OPTIONS}
                      className="h-8 w-28 text-xs"
                      aria-label={`Access for ${p.email}`}
                    />
                  ) : (
                    <Badge variant="secondary">
                      {p.role === "editor" ? "Can edit" : "Can view"}
                    </Badge>
                  )}
                  {(manager || p.user_id === me.user_id) && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => remove(p)}
                      aria-label={
                        p.user_id === me.user_id
                          ? "Leave project"
                          : `Remove ${p.email}`
                      }
                    >
                      {p.user_id === me.user_id ? <LogOut /> : <Trash2 />}
                    </Button>
                  )}
                </span>
              </li>
            ))}
            {manager && access.members.length === 0 && (
              <li className="rounded-md border border-dashed px-3 py-4 text-center text-sm text-muted-foreground">
                Only you can see this project.
              </li>
            )}
          </ul>
        </DialogContent>
      </Dialog>
    </>
  );
}
