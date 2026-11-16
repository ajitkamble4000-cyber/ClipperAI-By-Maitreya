"use client";

import { useEffect, useState } from "react";
import { Gift, Ticket, Users } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { siteUrl } from "@/lib/routes";

export function RedeemCard({ onDone }: { onDone?: () => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const redeem = async () => {
    setBusy(true);
    try {
      const r = await api<{ message: string }>("/promo/redeem", { method: "POST", json: { code } });
      toast.success(r.message);
      setCode("");
      onDone?.();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Ticket className="size-4" /> Have a code?
        </CardTitle>
        <CardDescription>Promo codes add bonus tokens or unlock a plan for a while.</CardDescription>
      </CardHeader>
      <CardContent className="flex gap-2">
        <Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="CODE" aria-label="Promo code" className="font-mono uppercase" maxLength={32} />
        <Button onClick={redeem} disabled={code.trim().length < 3 || busy} data-testid="redeem">
          Redeem
        </Button>
      </CardContent>
    </Card>
  );
}

interface Referrals {
  code: string;
  path: string;
  reward: number;
  joined: number;
  rewarded: number;
  tokens_earned: number;
  friends: { name: string; status: string; created_at: string }[];
}

export function ReferralCard() {
  const [r, setR] = useState<Referrals | null>(null);
  useEffect(() => {
    api<Referrals>("/referrals").then(setR).catch(() => {});
  }, []);
  if (!r) return null;
  const link = typeof window !== "undefined" ? siteUrl(r.path) : r.path;
  return (
    <Card data-testid="referral-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Gift className="size-4" /> Invite friends, get tokens
        </CardTitle>
        <CardDescription>
          When a friend signs up with your link and makes their first video, you both get {r.reward.toLocaleString()} bonus tokens.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex gap-2">
          <Input readOnly value={link} aria-label="Your invite link" data-testid="referral-link" onFocus={(e) => e.target.select()} />
          <Button variant="outline" onClick={() => navigator.clipboard.writeText(link).then(() => toast.success("Link copied")).catch(() => {})}>
            Copy
          </Button>
        </div>
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Users className="size-4" /> {r.joined} joined · {r.rewarded} made a video · {r.tokens_earned.toLocaleString()} tokens earned
        </p>
      </CardContent>
    </Card>
  );
}
