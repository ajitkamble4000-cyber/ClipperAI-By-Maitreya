"use client";

import { useEffect, useState } from "react";
import { Coins, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { env } from "@/lib/env";
import { type BillingCatalog, inr, payWithRazorpay } from "@/lib/razorpay";

/** Buy bonus-token packs with Razorpay (shown only when online payments are set up). */
export function TokenPacks({ onBought }: { onBought?: () => void }) {
  const [cat, setCat] = useState<BillingCatalog | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${env.apiUrl}/public/billing`)
      .then((r) => r.json())
      .then(setCat)
      .catch(() => {});
  }, []);

  if (!cat?.enabled || cat.packs.length === 0) return null;

  const buy = async (id: string) => {
    setBusy(id);
    try {
      const r = await payWithRazorpay({ kind: "tokens", pack_id: id });
      toast.success(`${(r.tokens ?? 0).toLocaleString()} tokens added. Thank you!`);
      onBought?.();
    } catch (e) {
      const msg = (e as Error).message;
      if (msg === "Payment cancelled") toast.message(msg);
      else toast.error(msg);
    } finally {
      setBusy(null);
    }
  };

  const perK = (p: BillingCatalog["packs"][number]) => (p.price_inr / (p.tokens / 1000)).toFixed(p.price_inr / (p.tokens / 1000) < 10 ? 1 : 0);

  return (
    <Card data-testid="token-packs">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Coins className="size-4 text-primary" /> Buy tokens
        </CardTitle>
        <CardDescription>Bonus tokens never expire and are used after your daily allowance. Pay with UPI, card, net banking or wallet.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-3">
        {cat.packs.map((p) => (
          <div key={p.id} className="flex flex-col rounded-xl border p-4" data-testid={`pack-${p.id}`}>
            <p className="text-sm font-medium">{p.name}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{p.tokens.toLocaleString()}</p>
            <p className="text-xs text-muted-foreground">tokens · ₹{perK(p)} per 1,000</p>
            <Button className="mt-3" onClick={() => buy(p.id)} disabled={!!busy} data-testid={`buy-pack-${p.id}`}>
              {busy === p.id ? <Loader2 className="animate-spin" /> : null}
              {busy === p.id ? "Opening…" : `Buy for ${inr(p.price_inr)}`}
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
