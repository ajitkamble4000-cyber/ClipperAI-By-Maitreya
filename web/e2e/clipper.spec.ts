import { expect, test } from "@playwright/test";
import { resolve } from "node:path";
import { createMember, login } from "./helpers";

const PODCAST = resolve(__dirname, "../../tests/fixtures/media/podcast.mp4");

test("clipper: upload → live progress → clip cards → edit, restyle, nudge, zip", async ({ page }) => {
  test.setTimeout(900_000);
  const a = await createMember("member");
  await login(page, a.email);
  await page.goto("/clipper/new");
  await page.getByRole("tab", { name: "Upload" }).click();
  await expect(page.getByTestId("file-input-source")).toBeAttached();
  await page.getByTestId("file-input-source").setInputFiles(PODCAST);
  await expect(page.getByText("Ready: podcast.mp4")).toBeVisible({ timeout: 60_000 });

  // 2 clips, 15–25 s (slider keyboard control)
  const num = page.getByRole("slider").first();
  await num.focus();
  for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowLeft");
  await page.getByTestId("preset-karaoke").click();
  await expect(page.getByTestId("caption-preview")).toBeVisible();
  await page.getByTestId("create-clips").click();

  await expect(page).toHaveURL(/\/clipper\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("job-progress")).toBeVisible();
  // Live progress: percent increases without reloading.
  const seen = new Set<string>();
  await expect
    .poll(async () => {
      const t = await page.getByTestId("job-percent").textContent().catch(() => null);
      if (t) seen.add(t);
      return seen.size;
    }, { timeout: 120_000 })
    .toBeGreaterThanOrEqual(3);

  // Survives a refresh mid-job.
  await page.reload();
  await expect(page.getByTestId("clip-card").first()).toBeVisible({ timeout: 300_000 });
  await expect(page.getByTestId("clip-card")).toHaveCount(2);
  await expect(page.getByTestId("clip-status")).toHaveText(["ready", "ready"], { timeout: 600_000 });
  await expect(page.locator("video").first()).toBeVisible();
  await expect(page.getByTestId("virality").first()).toBeVisible();

  // Edit title -> saved (survives reload).
  const title = page.getByLabel(/Title \(/).first();
  await title.fill("My edited title");
  await title.blur();
  await page.waitForTimeout(800);
  await page.reload();
  await expect(page.getByLabel(/Title \(/).first()).toHaveValue("My edited title");

  // Change caption style -> re-renders only captions.
  const firstCard = page.getByTestId("clip-card").first();
  await firstCard.getByRole("button", { name: "Change caption style" }).click();
  await page.getByTestId("preset-boxed").click();
  await page.getByTestId("apply-style").click();
  await expect(firstCard.getByTestId("clip-status")).not.toHaveText("ready", { timeout: 15_000 });
  await expect(firstCard.getByTestId("clip-status")).toHaveText("ready", { timeout: 300_000 });

  // Nudge start by +1s -> re-render with new timing.
  await firstCard.getByRole("button", { name: "start plus 1 second" }).click();
  await firstCard.getByRole("button", { name: "Apply & re-render" }).click();
  await expect(firstCard.getByTestId("clip-status")).not.toHaveText("ready", { timeout: 15_000 });
  await expect(firstCard.getByTestId("clip-status")).toHaveText("ready", { timeout: 300_000 });

  // Download all as ZIP.
  const download = page.waitForEvent("download", { timeout: 120_000 });
  await page.getByTestId("zip").click();
  const d = await download;
  expect(d.suggestedFilename()).toMatch(/\.zip$/);
});
