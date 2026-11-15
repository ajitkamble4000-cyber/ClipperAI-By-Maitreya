"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, OctagonX } from "lucide-react";
import { api } from "@/lib/api";

interface Budget {
  budget: number | null;
  spent: number;
  ratio: number;
  level: "ok" | "warn" | "blocked";
}

/** Team-wide warning at 80% of the monthly AI budget and a notice when premium generation is paused. */
export function BudgetBanner() {
  const [b, setB] = useState<Budget | null>(null);
  useEffect(() => {
    const load = () => api<Budget>("/budget").then(setB).catch(() => {});
    load();
    const id = setInterval(load, 120_000);
    return () => clearInterval(id);
  }, []);
  if (!b || b.level === "ok" || !b.budget) return null;
  const blocked = b.level === "blocked";
  return (
    <div
      role="status"
      data-testid="budget-banner"
      className={`mb-4 flex items-center gap-2 rounded-xl border px-3 py-2 text-sm ${blocked ? "border-destructive/40 bg-destructive/10" : "border-warning/40 bg-warning/10"}`}
    >
      {blocked ? <OctagonX className="size-4 text-destructive" /> : <AlertTriangle className="size-4 text-warning" />}
      <span>
        {blocked
          ? `Monthly AI budget reached ($${b.spent.toFixed(2)} of $${b.budget.toFixed(2)}). Image, voice and video generation are paused; clipping uses basic mode.`
          : `${Math.round(b.ratio * 100)}% of this month's AI budget is used ($${b.spent.toFixed(2)} of $${b.budget.toFixed(2)}).`}{" "}
        <Link href="/usage" className="underline">
          See usage
        </Link>
      </span>
    </div>
  );
}
