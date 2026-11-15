"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Coins, Infinity as InfinityIcon } from "lucide-react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { api } from "@/lib/api";
import { supabaseBrowser } from "@/lib/supabase/client";
import { realtimeAuth } from "@/lib/supabase/realtime";
import { cn } from "@/lib/utils";

import type { Wallet } from "./member-context";

export type { Wallet };

/** Live token balance (updates over Realtime whenever the wallet changes). */
export function useWallet(initial?: Wallet | null) {
  const [w, setW] = useState<Wallet | null>(initial ?? null);
  useEffect(() => {
    const sb = supabaseBrowser();
    let ch: RealtimeChannel | null = null;
    let alive = true;
    const load = () => api<Wallet>("/tokens").then((x) => alive && setW(x)).catch(() => {});
    load();
    realtimeAuth(sb).then(() => {
      if (!alive) return;
      ch = sb.channel("wallet").on("postgres_changes", { event: "*", schema: "public", table: "wallets" }, load).subscribe();
    });
    const id = setInterval(load, 60_000);
    return () => {
      alive = false;
      clearInterval(id);
      if (ch) sb.removeChannel(ch);
    };
  }, []);
  return w;
}

export function TokenChip({ initial, className }: { initial?: Wallet | null; className?: string }) {
  const w = useWallet(initial);
  if (!w) return null;
  const low = !w.unlimited && w.daily_allowance && w.total < w.daily_allowance * 0.15;
  return (
    <Link
      href="/account/tokens"
      data-testid="token-chip"
      title={w.unlimited ? "Unlimited tokens" : `${w.daily_balance} daily + ${w.bonus_balance} bonus · refills ${new Date(w.resets_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium tabular-nums",
        low ? "border-warning/50 text-warning" : "text-foreground",
        className,
      )}
    >
      {w.unlimited ? <InfinityIcon className="size-3.5 text-primary" /> : <Coins className="size-3.5 text-primary" />}
      {w.unlimited ? "Unlimited" : w.total.toLocaleString()}
    </Link>
  );
}
