"use client";

import type { SupabaseClient } from "@supabase/supabase-js";

/** Make sure Realtime uses the user's JWT (not the anon key) before subscribing, or RLS hides every event. */
export async function realtimeAuth(sb: SupabaseClient): Promise<void> {
  const { data } = await sb.auth.getSession();
  if (data.session?.access_token) await sb.realtime.setAuth(data.session.access_token);
}
