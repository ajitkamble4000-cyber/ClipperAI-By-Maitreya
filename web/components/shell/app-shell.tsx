"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, Clapperboard, LayoutGrid, LogOut, Scissors, Settings, Sparkles } from "lucide-react";
import { supabaseBrowser } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";
import { MemberProvider, type Me } from "./member-context";

const NAV = [
  { href: "/", label: "Library", icon: LayoutGrid },
  { href: "/clipper", label: "Clipper", icon: Scissors },
  { href: "/story", label: "Story Studio", icon: Sparkles },
  { href: "/usage", label: "Usage", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ me, children }: { me: Me; children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));
  const signOut = async () => {
    await supabaseBrowser().auth.signOut();
    router.replace("/login");
    router.refresh();
  };
  return (
    <MemberProvider me={me}>
      <div className="min-h-dvh md:grid md:grid-cols-[232px_1fr]">
        <aside className="sticky top-0 hidden h-dvh flex-col border-r bg-card/40 p-4 md:flex">
          <Link href="/" className="mb-8 flex items-center gap-2 px-2 font-semibold">
            <Clapperboard className="size-6 text-primary" /> Shorts Studio
          </Link>
          <nav className="grid gap-1">
            {NAV.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition",
                  active(n.href) ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                <n.icon className="size-4" /> {n.label}
              </Link>
            ))}
          </nav>
          <div className="mt-auto border-t pt-4">
            <p className="truncate px-2 text-sm font-medium">{me.display_name ?? me.email}</p>
            <p className="px-2 text-xs capitalize text-muted-foreground">{me.role}</p>
            <button onClick={signOut} className="mt-2 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-muted-foreground hover:bg-accent">
              <LogOut className="size-4" /> Sign out
            </button>
          </div>
        </aside>
        <header className="sticky top-0 z-30 flex items-center justify-between border-b bg-background/80 px-4 py-3 backdrop-blur md:hidden">
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <Clapperboard className="size-5 text-primary" /> Shorts Studio
          </Link>
          <button onClick={signOut} aria-label="Sign out" className="rounded-lg p-2 text-muted-foreground">
            <LogOut className="size-4" />
          </button>
        </header>
        <main className="min-w-0 px-4 pb-24 pt-6 md:px-8 md:pb-10">{children}</main>
        <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t bg-background/95 backdrop-blur md:hidden">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={cn("flex flex-col items-center gap-1 py-2 text-[11px]", active(n.href) ? "text-primary" : "text-muted-foreground")}
            >
              <n.icon className="size-5" />
              {n.label.split(" ")[0]}
            </Link>
          ))}
        </nav>
      </div>
    </MemberProvider>
  );
}
