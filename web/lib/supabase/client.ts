"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import { env } from "@/lib/env";

let client: SupabaseClient | null = null;

export function supabaseBrowser(): SupabaseClient {
  // A static build made before the server addresses were set has no key: use a placeholder so public pages still
  // load (nobody can sign in until it's configured; see env.configured).
  if (!client) client = createBrowserClient(env.supabaseUrl, env.supabaseAnonKey || "not-configured");
  return client;
}
