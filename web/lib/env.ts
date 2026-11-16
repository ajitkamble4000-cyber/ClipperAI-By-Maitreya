const STATIC = process.env.NEXT_PUBLIC_STATIC === "1";
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "";

export const env = {
  supabaseUrl: supabaseUrl || "http://127.0.0.1:54321",
  supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "",
  apiUrl: (apiUrl || "http://127.0.0.1:8000").replace(/\/$/, ""),
  /** False on a static (GitHub Pages) build made before the server addresses were set: the website still works,
   *  but signing in can't until NEXT_PUBLIC_SUPABASE_URL / _ANON_KEY / NEXT_PUBLIC_API_URL are provided. */
  configured: !STATIC || Boolean(supabaseUrl && apiUrl && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY),
};
