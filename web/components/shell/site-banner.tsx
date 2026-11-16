"use client";

import { useEffect, useState } from "react";
import { Wrench } from "lucide-react";
import { env } from "@/lib/env";

export interface SiteStatus {
  signups_open: boolean;
  jobs_paused: boolean;
  maintenance_message: string;
  referral_reward: number;
}

let cached: Promise<SiteStatus | null> | null = null;
export function siteStatus(): Promise<SiteStatus | null> {
  cached ??= fetch(`${env.apiUrl}/public/site`, { cache: "no-store" })
    .then((r) => (r.ok ? (r.json() as Promise<SiteStatus>) : null))
    .catch(() => null);
  return cached;
}

export function useSiteStatus() {
  const [s, setS] = useState<SiteStatus | null>(null);
  useEffect(() => {
    siteStatus().then(setS);
  }, []);
  return s;
}

/** The owner's maintenance message, shown at the top of every page while it's set. */
export function SiteBanner() {
  const s = useSiteStatus();
  if (!s || (!s.maintenance_message && !s.jobs_paused)) return null;
  return (
    <div className="flex items-center justify-center gap-2 bg-warning/15 px-4 py-2 text-center text-sm" role="status" data-testid="site-banner">
      <Wrench className="size-4 shrink-0 text-warning" />
      {s.maintenance_message || "New jobs are paused for maintenance. Everything you made is safe."}
    </div>
  );
}
