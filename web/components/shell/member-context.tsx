"use client";

import { createContext, useContext } from "react";

export interface Plan {
  id: string;
  name: string;
  daily_tokens: number | null;
  price_usd_month: number;
  features: string[];
  limits: Record<string, number | boolean>;
}

export interface Me {
  user_id: string;
  email: string;
  role: "owner" | "admin" | "user";
  display_name: string | null;
  plan_id: string;
  team: "staff" | "creator" | null;
  unlimited: boolean;
  plan: Plan;
  features: string[];
  limits: Record<string, number | boolean>;
  onboarding: Record<string, boolean>;
}

const Ctx = createContext<Me | null>(null);

export function MemberProvider({ me, children }: { me: Me; children: React.ReactNode }) {
  return <Ctx.Provider value={me}>{children}</Ctx.Provider>;
}

export function useMe(): Me {
  const me = useContext(Ctx);
  if (!me) throw new Error("useMe outside MemberProvider");
  return me;
}

export const isAdmin = (me: Me) => me.role === "owner" || me.role === "admin";
export const hasFeature = (me: Me, f: string) => me.unlimited || me.features.includes(f);
export const limit = (me: Me, k: string, fallback = 0) => Number(me.limits?.[k] ?? fallback);
