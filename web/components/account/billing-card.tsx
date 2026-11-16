"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Receipt } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { inr } from "@/lib/razorpay";

interface Payment {
  id: string;
  kind: "plan" | "tokens";
  description: string;
  amount: number;
  currency: string;
  status: "paid" | "failed" | "refunded";
  created_at: string;
  paid_at: string | null;
  payment_id: string | null;
}
export interface MyBilling {
  plan_id: string;
  plan_name: string;
  plan_source: "trial" | "paid" | null;
  plan_expires_at: string | null;
  plan_before_trial: string | null;
  payments: Payment[];
  enabled: boolean;
}

export function useMyBilling() {
  const [b, setB] = useState<MyBilling | null>(null);
  useEffect(() => {
    api<MyBilling>("/billing/me").then(setB).catch(() => {});
  }, []);
  return b;
}

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });

/** "Pro until 16 Dec 2026" (paid) or the trial note, under the plan badge. */
export function PlanTerm({ billing }: { billing: MyBilling | null }) {
  if (!billing?.plan_expires_at) return null;
  if (billing.plan_source === "paid") {
    return (
      <p className="flex flex-wrap items-center gap-2 text-sm" data-testid="paid-until">
        <span>
          {billing.plan_name} paid until <b>{day(billing.plan_expires_at)}</b>, then back to {(billing.plan_before_trial ?? "free").replace(/^./, (c) => c.toUpperCase())}.
        </span>
        {billing.enabled && (
          <Link href="/pricing" className="text-primary hover:underline">
            Renew
          </Link>
        )}
      </p>
    );
  }
  return (
    <p className="text-sm text-primary" data-testid="trial-note">
      Trial: {billing.plan_name} until {new Date(billing.plan_expires_at).toLocaleDateString(undefined, { day: "numeric", month: "long" })}, then back to
      your previous plan.
    </p>
  );
}

/** Your Razorpay payments. */
export function BillingHistory({ billing }: { billing: MyBilling | null }) {
  if (!billing || billing.payments.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Receipt className="size-4" /> Payments
        </CardTitle>
        <CardDescription>Razorpay also emails you a receipt for every payment.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y text-sm" data-testid="payments">
          {billing.payments.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="min-w-0">
                <span className="block truncate">{p.description}</span>
                <span className="block text-xs text-muted-foreground">
                  {day(p.paid_at ?? p.created_at)}
                  {p.payment_id ? ` · ${p.payment_id}` : ""}
                </span>
              </span>
              <span className="flex items-center gap-2">
                <span className="tabular-nums">{inr(p.amount / 100)}</span>
                <Badge variant={p.status === "paid" ? "success" : p.status === "failed" ? "destructive" : "secondary"} className="capitalize">
                  {p.status}
                </Badge>
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
