import { expect, test } from "@playwright/test";
import { createMember, login, SUPABASE } from "./helpers";

test.skip(process.env.STUDIO_FAKE_GEMINI !== "1", "run with STUDIO_FAKE_GEMINI=1");

const SERVICE =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU";
const H = { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, "Content-Type": "application/json" };

async function setModels(models: Record<string, string>) {
  await fetch(`${SUPABASE}/rest/v1/settings?id=eq.1`, { method: "PATCH", headers: H, body: JSON.stringify({ models }) });
}

test("premium: pick scenes, confirm the estimated cost, Veo clips, render", async ({ page }) => {
  test.setTimeout(600_000);
  await setModels({ video: "veo-3.1-fast-generate-preview" });
  try {
    const a = await createMember("member");
    await login(page, a.email);
    await page.goto("/story/new");
    await page.getByLabel("Story idea").fill("What happens if the sun went out");
    await page.getByTestId("write-script").click();
    await expect(page.getByTestId("scene-card")).toHaveCount(6, { timeout: 60_000 });
    await page.getByRole("tab", { name: "3. Images" }).click();
    await page.getByTestId("generate-images").click();
    await expect(page.getByTestId("scene-image").locator("img")).toHaveCount(6, { timeout: 120_000 });
    await page.getByRole("tab", { name: "4. Voice" }).click();
    await page.getByTestId("generate-voice").click();
    await expect(page.getByTestId("scene-timings")).toBeVisible({ timeout: 180_000 });

    await page.getByRole("tab", { name: "5. Render" }).click();
    await page.getByRole("button", { name: "Premium AI video" }).click();
    await page.getByLabel("Use AI video for scene 1").check();
    await page.getByLabel("Use AI video for scene 2").check();
    await page.getByTestId("veo-generate").click();
    await expect(page.getByTestId("veo-cost")).toHaveText(/^\$\d+\.\d\d$/);
    await page.getByTestId("veo-confirm").click();
    await expect(page.getByTestId("veo-scene").filter({ hasText: "video" })).toHaveCount(2, { timeout: 120_000 });
    await page.getByTestId("render").click();
    await expect(page.getByTestId("story-video")).toBeVisible({ timeout: 300_000 });
  } finally {
    await setModels({});
  }
});
