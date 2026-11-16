"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, CalendarDays, Home, LayoutGrid, LogOut, Scissors, Settings, Shield, Sparkles, UserRound } from "lucide-react";
import { supabaseBrowser } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";
import { BudgetBanner } from "./budget-banner";
import { TokenChip } from "./token-chip";
import { isAdmin, MemberProvider, type Me } from "./member-context";
import { NotificationBell } from "./notification-bell";
import { SiteBanner } from "./site-banner";
import { BrandMark } from "./brand-mark";

type NavItem = { href: string; label: string; icon: typeof Home; admin?: boolean; owner?: boolean };

const NAV: NavItem[] = [
  { href: "/", label: "Home", icon: Home },
  { href: "/clipper", label: "Clipper", icon: Scissors },
  { href: "/story", label: "Story Studio", icon: Sparkles },
  { href: "/library", label: "Library", icon: LayoutGrid },
  { href: "/calendar", label: "Calendar", icon: CalendarDays },
  { href: "/account", label: "Account", icon: UserRound },
  { href: "/admin", label: "Admin", icon: Shield, admin: true },
  { href: "/usage", label: "Usage", icon: BarChart3, admin: true },
  { href: "/settings", label: "Settings", icon: Settings, admin: true },
];
const MOBILE = ["/", "/clipper", "/story", "/library", "/account"];

export function AppShell({ me, children }: { me: Me; children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));
  const nav = NAV.filter((n) => !n.admin || isAdmin(me));
  const signOut = async () => {
    await supabaseBrowser().auth.signOut();
    router.replace("/login");
    router.refresh();
  };
  return (
    <MemberProvider me={me}>
      <div className="min-h-dvh md:grid md:grid-cols-[232px_1fr]">
        <div className="hidden border-r bg-card/40 md:block">
        <aside className="sticky top-0 flex h-dvh flex-col p-4">
          <div className="mb-8 flex items-center justify-between gap-2 px-2">
            <Link href="/" className="min-w-0">
              <BrandMark />
            </Link>
            <NotificationBell align="left" />
          </div>
          <nav className="grid gap-1">
            {nav.map((n) => (
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
            <TokenChip className="mx-2 mb-3" initial={me.wallet} />
            <p className="truncate px-2 text-sm font-medium">{me.display_name ?? me.email}</p>
            <p className="px-2 text-xs text-muted-foreground">
              {me.role === "owner" ? "Owner" : me.role === "admin" ? "Admin" : me.team ? `${me.team[0].toUpperCase()}${me.team.slice(1)} team` : `${me.plan.name} plan`}
            </p>
            <button onClick={signOut} className="mt-2 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-muted-foreground hover:bg-accent">
              <LogOut className="size-4" /> Sign out
            </button>
          </div>
        </aside>
        </div>
        <header className="sticky top-0 z-30 flex items-center justify-between border-b bg-background/80 px-4 py-3 backdrop-blur md:hidden">
          <Link href="/" className="min-w-0">
            <BrandMark size="sm" />
          </Link>
          <TokenChip className="ml-auto mr-1" initial={me.wallet} />
          <NotificationBell />
        </header>
        <main className="min-w-0 px-4 pb-24 pt-6 md:px-8 md:pb-10">
          <div className="-mx-4 -mt-6 mb-6 md:-mx-8">
            <SiteBanner />
          </div>
          <BudgetBanner />
          {children}
        </main>
        <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t bg-background/95 backdrop-blur md:hidden">
          {NAV.filter((n) => MOBILE.includes(n.href)).map((n) => (
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
