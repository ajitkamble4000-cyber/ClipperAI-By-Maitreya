"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ShieldAlert } from "lucide-react";
import { isAdmin, useMe } from "@/components/shell/member-context";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/requests", label: "Upgrade requests" },
  { href: "/admin/jobs", label: "Jobs" },
  { href: "/admin/plans", label: "Plans & prices" },
  { href: "/admin/announcements", label: "Announcements" },
  { href: "/admin/audit", label: "Audit log" },
  { href: "/admin/health", label: "System health" },
  { href: "/settings", label: "AI & storage settings" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const path = usePathname();
  if (!isAdmin(me)) {
    return (
      <div className="mt-20 text-center">
        <ShieldAlert className="mx-auto size-8 text-muted-foreground" />
        <h1 className="mt-3 text-xl font-semibold">Admins only</h1>
        <p className="mt-1 text-sm text-muted-foreground">This area is for the owner and admins.</p>
      </div>
    );
  }
  return (
    <div className="grid gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Admin</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {me.role === "owner" ? "Owner & founder: you can manage everything, including admins." : "Admin: manage users, tokens, jobs and announcements."}
        </p>
      </div>
      <nav className="-mx-4 flex gap-1 overflow-x-auto border-b px-4 md:mx-0 md:px-0" aria-label="Admin sections">
        {TABS.map((t) => {
          const active = t.href === "/admin" ? path === "/admin" : path.startsWith(t.href);
          return (
            <Link
              key={t.href}
              href={t.href}
              className={cn(
                "shrink-0 border-b-2 px-3 py-2 text-sm transition",
                active ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </Link>
          );
        })}
      </nav>
      {children}
    </div>
  );
}
