"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AppShell } from "@/components/shell/app-shell";
import type { Me } from "@/components/shell/member-context";
import { env } from "@/lib/env";
import { supabaseBrowser } from "@/lib/supabase/client";

/**
 * The signed-in area on static hosting (no server): checks the session in the browser, sends visitors to the
 * landing page or sign-in (like the middleware does on the server build), then loads the profile from the API.
 */
export function ClientStudio({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [problem, setProblem] = useState<{ text: string; email?: string } | null>(null);

  useEffect(() => {
    if (!env.configured) {
      router.replace("/welcome"); // not connected to a server yet: only the public pages work
      return;
    }
    const sb = supabaseBrowser();
    let alive = true;
    (async () => {
      const {
        data: { session },
      } = await sb.auth.getSession();
      if (!session) {
        const search = typeof window !== "undefined" ? window.location.search : "";
        router.replace(path === "/" ? "/welcome" : `/login?next=${encodeURIComponent(path + search)}`);
        return;
      }
      try {
        const r = await fetch(`${env.apiUrl}/me`, { headers: { Authorization: `Bearer ${session.access_token}` }, cache: "no-store" });
        if (!alive) return;
        if (r.ok) setMe((await r.json()) as Me);
        else {
          const detail = ((await r.json().catch(() => ({}))) as { detail?: string }).detail;
          setProblem({ text: detail ?? `Error ${r.status}`, email: session.user.email });
        }
      } catch {
        if (alive) setProblem({ text: "The server is unreachable right now. Try again in a minute.", email: session.user.email });
      }
    })();
    const { data } = sb.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_OUT") router.replace("/login");
    });
    return () => {
      alive = false;
      data.subscription.unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- check once per visit, not on every navigation
  }, []);

  if (problem) {
    return (
      <div className="flex min-h-dvh items-center justify-center px-4 text-center">
        <div>
          <h1 className="text-xl font-semibold">We can&apos;t open your workspace</h1>
          <p className="mt-2 text-sm text-muted-foreground">{problem.text}</p>
          {problem.email && <p className="mt-1 text-xs text-muted-foreground">Signed in as {problem.email}</p>}
        </div>
      </div>
    );
  }
  if (!me) {
    return (
      <div className="flex min-h-dvh items-center justify-center" aria-label="Loading">
        <div className="size-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }
  return <AppShell me={me}>{children}</AppShell>;
}
