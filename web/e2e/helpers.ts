import { expect, type Page } from "@playwright/test";

export const SUPABASE = "http://127.0.0.1:54321";
const SERVICE =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU";
const admin = { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, "Content-Type": "application/json" };

export const PASSWORD = "e2e-password-123";

export async function createMember(
  role: "owner" | "admin" | "member" | "user",
  email = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 6)}@example.com`,
  extra?: Record<string, unknown>,
) {
  const r = await fetch(`${SUPABASE}/auth/v1/admin/users`, {
    method: "POST",
    headers: admin,
    body: JSON.stringify({ email, password: PASSWORD, email_confirm: true }),
  });
  const user = await r.json();
  // The sign-up trigger creates the profile; set the role (and optional team/plan) for the test.
  const m = await fetch(`${SUPABASE}/rest/v1/members?user_id=eq.${user.id}`, {
    method: "PATCH",
    headers: { ...admin, Prefer: "return=minimal" },
    body: JSON.stringify({ role: role === "member" ? "user" : role, display_name: `E2E ${role}`, ...(extra ?? {}) }),
  });
  if (!m.ok) throw new Error(await m.text());
  return { id: user.id as string, email };
}

export async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Library" })).toBeVisible();
}

export async function latestEmailLink(to: string): Promise<string> {
  for (let i = 0; i < 30; i++) {
    const r = await fetch(`http://127.0.0.1:54324/api/v1/search?query=${encodeURIComponent(`to:${to}`)}`);
    const j = await r.json();
    if (j.messages?.length) {
      const msg = await (await fetch(`http://127.0.0.1:54324/api/v1/message/${j.messages[0].ID}`)).json();
      const m = (msg.HTML || msg.Text).match(/href="([^"]+)"/) ?? (msg.Text as string).match(/(https?:\/\/\S+)/);
      if (m) return m[1].replace(/&amp;/g, "&");
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`no email for ${to}`);
}
