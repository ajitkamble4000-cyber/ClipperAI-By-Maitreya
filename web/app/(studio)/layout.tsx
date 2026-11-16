import { redirect } from "next/navigation";
import { AppShell } from "@/components/shell/app-shell";
import { ClientStudio } from "@/components/shell/client-studio";
import type { Me } from "@/components/shell/member-context";
import { env } from "@/lib/env";
import { STATIC } from "@/lib/routes";
import { supabaseServer } from "@/lib/supabase/server";

export default async function StudioLayout({ children }: { children: React.ReactNode }) {
  if (STATIC) return <ClientStudio>{children}</ClientStudio>; // static hosting: checked in the browser
  const sb = await supabaseServer();
  const {
    data: { user },
  } = await sb.auth.getUser();
  if (!user) redirect("/login");
  const {
    data: { session },
  } = await sb.auth.getSession();
  let me: Me | null = null;
  let problem: string | null = null;
  try {
    const r = await fetch(`${env.apiUrl}/me`, { headers: { Authorization: `Bearer ${session?.access_token ?? ""}` }, cache: "no-store" });
    if (r.ok) me = (await r.json()) as Me;
    else problem = ((await r.json().catch(() => ({}))) as { detail?: string }).detail ?? `Error ${r.status}`;
  } catch {
    problem = "The server is unreachable right now. Try again in a minute.";
  }
  if (!me) {
    return (
      <div className="flex min-h-dvh items-center justify-center px-4 text-center">
        <div>
          <h1 className="text-xl font-semibold">We can't open your workspace</h1>
          <p className="mt-2 text-sm text-muted-foreground">{problem}</p>
          <p className="mt-1 text-xs text-muted-foreground">Signed in as {user.email}</p>
        </div>
      </div>
    );
  }
  return <AppShell me={me}>{children}</AppShell>;
}
