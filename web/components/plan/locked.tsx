"use client";

import { Lock } from "lucide-react";
import { toast } from "sonner";
import { hasFeature, useMe } from "@/components/shell/member-context";
import { FEATURES } from "@/lib/features";
import { cn } from "@/lib/utils";

/** Small "Pro" / "Business" badge with a lock, shown next to options the user's plan doesn't include. */
export function LockedBadge({ feature, className }: { feature: string; className?: string }) {
  const me = useMe();
  if (hasFeature(me, feature)) return null;
  const f = FEATURES[feature];
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary", className)}
      data-testid={`locked-${feature}`}
    >
      <Lock className="size-3" aria-hidden /> {f?.plan ?? "Pro"}
    </span>
  );
}

/** `allowed(feature)` for the current user; `explain(feature)` shows the upgrade toast. */
export function useGate() {
  const me = useMe();
  const allowed = (feature: string) => hasFeature(me, feature);
  const explain = (feature: string) => {
    const f = FEATURES[feature];
    toast.message(`${f?.label ?? "This"} is part of ${f?.plan ?? "Pro"}`, {
      id: `locked-${feature}`, // one toast per feature, even if a control fires twice
      description: "Upgrade to unlock it, or keep going with the free options.",
      action: { label: "See plans", onClick: () => (window.location.href = "/pricing") },
    });
  };
  /** Wraps a setter so locked options explain themselves instead of turning on. */
  const guard =
    <T,>(feature: string, set: (v: T) => void) =>
    (v: T) => {
      if (!allowed(feature) && v) return explain(feature);
      set(v);
    };
  return { allowed, explain, guard };
}
