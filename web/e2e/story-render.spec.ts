import { expect, test } from "@playwright/test";
import { createMember, login } from "./helpers";

// Needs the worker started with STUDIO_FAKE_GEMINI=1 (offline fake: Pillow images + espeak voice).
test.skip(process.env.STUDIO_FAKE_GEMINI !== "1", "run with STUDIO_FAKE_GEMINI=1");

test("story studio: idea → script → characters → images → voice → render → download", async ({ page }) => {
  test.setTimeout(600_000);
  const a = await createMember("member");
  await login(page, a.email);
  await page.goto("/story/new");
  await page.getByLabel("Story idea").fill("What happens if you fall into a black hole");
  await page.getByTestId("write-script").click();
  await expect(page.getByTestId("scene-card")).toHaveCount(6, { timeout: 60_000 });

  await page.getByRole("tab", { name: "2. Characters" }).click();
  await expect(page.getByTestId("character-card")).toHaveCount(1);
  await page.getByRole("button", { name: "Generate missing references" }).click();
  await expect(page.getByTestId("character-card").locator("img")).toBeVisible({ timeout: 60_000 });

  await page.getByRole("tab", { name: "3. Images" }).click();
  await page.getByTestId("generate-images").click();
  await expect(page.getByTestId("scene-image").locator("img")).toHaveCount(6, { timeout: 120_000 });
  // Edit one image with a prompt.
  const first = page.getByTestId("scene-image").first();
  await first.getByPlaceholder("Edit: make it night time").fill("make it night time");
  await first.getByRole("button", { name: "Apply edit" }).click();

  await page.getByRole("tab", { name: "4. Voice" }).click();
  await page.getByTestId("generate-voice").click();
  await expect(page.getByTestId("scene-timings")).toBeVisible({ timeout: 180_000 });
  await expect(page.locator("audio")).toBeVisible();

  await page.getByRole("tab", { name: "5. Render" }).click();
  await page.getByTestId("render").click();
  await expect(page.getByTestId("story-video")).toBeVisible({ timeout: 300_000 });
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download MP4" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.mp4$/);
});
