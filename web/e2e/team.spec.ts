import { expect, test } from "@playwright/test";
import { createMember, login, SUPABASE } from "./helpers";

const SERVICE =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU";
const H = { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, "Content-Type": "application/json", Prefer: "return=minimal" };

async function rest(path: string, method: string, body?: unknown) {
  return fetch(`${SUPABASE}/rest/v1/${path}`, { method, headers: H, body: body ? JSON.stringify(body) : undefined });
}

test("admin settings, budget warning banner, usage dashboard; members see no admin tabs", async ({ page, browser }) => {
  const admin = await createMember("admin");
  await rest("usage_events", "POST", [
    { user_id: admin.id, model: "e2e-model-image", kind: "image", images: 3, input_tokens: 0, output_tokens: 0, cost_usd: 8.6 },
    { user_id: admin.id, model: "e2e-model-text", kind: "text", images: 0, input_tokens: 5000, output_tokens: 900, cost_usd: 0.02 },
  ]);
  try {
    await login(page, admin.email);
    await page.goto("/settings");
    await expect(page.getByRole("tab", { name: "AI & budget" })).toBeVisible();
    await expect(page.getByText("Not set").first()).toBeVisible();
    await page.getByLabel("Monthly budget").fill("12");
    await page.getByRole("button", { name: "Save budget" }).click();
    await expect(page.getByText("Budget saved")).toBeVisible();

    await page.goto("/usage");
    await expect(page.getByTestId("budget-banner")).toContainText("% of this month's AI budget");
    await expect(page.getByRole("img", { name: "Daily AI spend, last 30 days" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "e2e-model-image" }).first()).toBeVisible();
    await page.screenshot({ path: "test-results/usage.png", fullPage: true });

    await page.goto("/settings?tab=pricing");
    await expect(page.getByLabel("veo-3.1-fast Per video s")).toBeVisible();

    const member = await createMember("member");
    const ctx = await browser.newContext();
    const p2 = await ctx.newPage();
    await login(p2, member.email);
    await p2.goto("/settings");
    await expect(p2.getByRole("tab", { name: "AI & budget" })).toHaveCount(0);
    await expect(p2.getByRole("tab", { name: "Members" })).toBeVisible();
    await expect(p2.getByTestId("budget-banner")).toBeVisible();
    await ctx.close();
  } finally {
    await rest("settings?id=eq.1", "PATCH", { monthly_budget_usd: null });
    await rest("usage_events?model=like.e2e-model-*", "DELETE");
  }
});

test("library: filters by type and creator, search", async ({ page }) => {
  const a = await createMember("member");
  const b = await createMember("member");
  const stamp = Date.now();
  await rest("projects", "POST", [
    { type: "clip", title: `Alpha clip ${stamp}`, created_by: a.id, status: "ready" },
    { type: "story", title: `Beta story ${stamp}`, created_by: b.id, status: "draft" },
  ]);
  await login(page, a.email);
  await page.getByLabel("Search").fill(String(stamp));
  await expect(page.getByTestId("library-grid").getByRole("link")).toHaveCount(2);
  await page.getByLabel("Search").fill(`Beta story ${stamp}`);
  await expect(page.getByTestId("library-grid").getByRole("link")).toHaveCount(1);
  await page.goto("/clipper");
  await page.getByLabel("Search").fill(String(stamp));
  await expect(page.getByTestId("library-grid").getByRole("link")).toHaveCount(1);
  await expect(page.getByText(`Alpha clip ${stamp}`)).toBeVisible();
});
