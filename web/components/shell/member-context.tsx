"use client";

import { createContext, useContext } from "react";

export interface Me {
  user_id: string;
  email: string;
  role: "admin" | "member";
  display_name: string | null;
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
