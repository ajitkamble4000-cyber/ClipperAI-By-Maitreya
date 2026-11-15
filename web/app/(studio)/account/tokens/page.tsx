"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowDownRight, Coins, Gift, Infinity as InfinityIcon, RefreshCcw, RotateCcw } from "lucide-react";
import { PageHeader } from "@/components/shell/page-header";
import { useMe } from "@/components/shell/member-context";
import { useWallet } from "@/components/shell/token-chip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Entry {
  id: number;
  ts: string;
  delta: number;
  bucket: string;
  reason: string;
  action: string | null;
  job_id: string | null;
  daily_after: number;
  bonus_after: number;
  meta: Record<string, unknown>;
  project_title: string | null;
}
interface Price {
  action: string;
  label: string;
  tokens: number;
  unit: string;
  description: string;
}

const REASON: Record<string, { label: string; icon: typeof Coins }> = {
  charge: { label: "Spent", icon: ArrowDownRight },
  refund: { label: "Refunded", icon: RotateCcw },
  adjust: { label: "Returned", icon: RotateCcw },
  grant: { label: "Gift from the team", icon: Gift },
  revoke: { label: "Removed by the team", icon: ArrowDownRight },
  daily_refill: { label: "Daily refill", icon: RefreshCcw },
  waived: { label: "Free for your team", icon: InfinityIcon },
};

export default function TokensPage() {
  const me = useMe();
  const w = useWallet(me.wallet);
  const [rows, setRows] = useState<Entry[] | null>(null);
  const [prices, setPrices] = useState<Price[]>([]);
  const [labels, setLabels] = useState<Record<string, string>>({});

  useEffect(() => {
    api<Entry[]>("/tokens/ledger?limit=100").then(setRows).catch(() => setRows([]));
    api<Price[]>("/tokens/prices")
      .then((p) => {
        setPrices(p.filter((x) => x.tokens > 0));
        setLabels(Object.fromEntries(p.map((x) => [x.action, x.label])));
      })
      .catch(() => {});
  }, []);

  const kindLabel = (a: string | null) =>
    a ? ({ clip: "Clipper", clip_rerender: "Re-render", story_render: "Story render", story_veo: "AI video" } as Record<string, string>)[a] ?? labels[a] ?? a.replace(/_/g, " ") : "";

  return (
    <div className="grid max-w-4xl gap-6">
      <PageHeader title="Tokens" description="Your daily allowance refills every day at midnight UTC. Bonus tokens never expire." />

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">Available</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold tabular-nums" data-testid="tokens-total">
              {w?.unlimited ? "Unlimited" : (w?.total ?? 0).toLocaleString()}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">Today's allowance</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold tabular-nums">{w?.unlimited ? "∞" : (w?.daily_balance ?? 0).toLocaleString()}</p>
            {!w?.unlimited && (
              <p className="text-xs text-muted-foreground">
                of {w?.daily_allowance?.toLocaleString()} · refills {w ? new Date(w.resets_at).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" }) : ""}
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">Bonus</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold tabular-nums">{w?.unlimited ? "∞" : (w?.bonus_balance ?? 0).toLocaleString()}</p>
            <p className="text-xs text-muted-foreground">Spent after the daily allowance</p>
          </CardContent>
        </Card>
      </div>
      {!me.unlimited && (
        <p className="text-sm text-muted-foreground">
          Need more every day?{" "}
          <Link href="/pricing" className="text-primary hover:underline">
            Upgrade your plan
          </Link>
          .
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle>History</CardTitle>
        </CardHeader>
        <CardContent>
          {!rows ? (
            <Skeleton className="h-40" />
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No activity yet.</p>
          ) : (
            <ul className="divide-y" data-testid="ledger">
              {rows.map((r) => {
                const R = REASON[r.reason] ?? { label: r.reason, icon: Coins };
                const tokensForWaived = r.reason === "waived" ? Number(r.meta?.tokens ?? 0) : 0;
                return (
                  <li key={r.id} className="flex items-center gap-3 py-2.5 text-sm">
                    <R.icon className={cn("size-4 shrink-0", r.delta > 0 ? "text-success" : r.delta < 0 ? "text-muted-foreground" : "text-primary")} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">
                        {R.label}
                        {r.action ? ` · ${kindLabel(r.action)}` : ""}
                        {r.project_title ? ` · ${r.project_title}` : ""}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {new Date(r.ts).toLocaleString()}
                        {typeof r.meta?.why === "string" ? ` · ${r.meta.why}` : ""}
                        {typeof r.meta?.note === "string" && r.meta.note ? ` · ${r.meta.note}` : ""}
                      </span>
                    </span>
                    <span className={cn("tabular-nums font-medium", r.delta > 0 ? "text-success" : "")}>
                      {r.reason === "waived" ? <span className="text-xs text-muted-foreground line-through">{tokensForWaived}</span> : r.delta > 0 ? `+${r.delta}` : r.delta}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>What things cost</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 sm:grid-cols-2">
          {prices.map((p) => (
            <div key={p.action} className="flex justify-between gap-3 rounded-lg border p-2.5 text-sm">
              <span>
                {p.label}
                <span className="block text-xs text-muted-foreground">{p.description}</span>
              </span>
              <span className="shrink-0 tabular-nums">
                {p.tokens} <span className="text-xs text-muted-foreground">/ {p.unit}</span>
              </span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
