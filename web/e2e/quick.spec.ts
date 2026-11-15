import { expect, test } from "@playwright/test";
import { resolve } from "node:path";
import { createMember, login } from "./helpers";

// Needs the worker started with STUDIO_FAKE_GEMINI=1 (offline fake AI).
test.skip(process.env.STUDIO_FAKE_GEMINI !== "1", "run with STUDIO_FAKE_GEMINI=1");

const PODCAST = resolve(__dirname, "../../tests/fixtures/media/podcast.mp4");

test("any link: platform detection, plan locks and token estimate (free plan)", async ({ page }) => {
  const a = await createMember("member");
  await login(page, a.email);
  await page.goto(`/clipper/new?url=${encodeURIComponent("https://www.instagram.com/reel/Cabc123/")}`);
  await expect(page.getByTestId("platform-chip")).toHaveText(/Instagram/);
  await expect(page.getByTestId("link-preview")).toContainText("cookies.txt");
  await page.getByLabel("Video link").fill("https://vm.tiktok.com/ZM123abc/");
  await expect(page.getByTestId("platform-chip")).toHaveText(/TikTok/);

  // Pro-only options explain themselves instead of turning on.
  await expect(page.getByTestId("locked-output_formats").first()).toBeVisible();
  await page.getByTestId("aspect-16:9").click();
  await expect(page.getByText("Square / 4:5 / 16:9 output is part of Pro")).toBeVisible();
  await expect(page.getByTestId("aspect-9:16")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("remove-silence").click();
  await expect(page.getByText("Filler & silence removal is part of Pro")).toBeVisible();
  await expect(page.getByTestId("remove-silence")).toHaveAttribute("data-state", "unchecked");
  await page.getByTestId("batch-tab").click();
  await expect(page.getByText("Batch mode is part of Business")).toBeVisible();

  // Live token estimate follows the mode.
  await page.getByTestId("mode-captions").click();
  await expect(page.getByTestId("quote")).toContainText("40 tokens");
  await page.getByTestId("mode-clips").click();
  await expect(page.getByTestId("quote")).toContainText(/\d+ tokens/);
});

test("auto mode on a short upload: captioned whole, caption files download (free plan, watermark)", async ({ page }) => {
  test.setTimeout(600_000);
  const a = await createMember("member");
  await login(page, a.email);
  await page.goto("/clipper/new");
  await page.getByRole("tab", { name: "Upload" }).click();
  await page.getByTestId("file-input-source").setInputFiles(PODCAST);
  await expect(page.getByText("Ready: podcast.mp4")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("mode-auto")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("create-clips").click();

  await expect(page).toHaveURL(/\/clipper\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("clip-status")).toHaveText("ready", { timeout: 480_000 });
  await expect(page.getByTestId("clip-card")).toHaveCount(1);
  await expect(page.getByTestId("whole-badge")).toBeVisible();
  await expect(page.getByTestId("project-title")).toHaveText("A quick captioned video");
  await expect(page.getByTestId("project-summary")).toContainText("Whole video with captions");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download SRT captions" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.srt$/);
});

test("pro: captions mode, square format, translated captions, jump cuts", async ({ page }) => {
  test.setTimeout(600_000);
  const a = await createMember("member", undefined, { plan_id: "pro" });
  await login(page, a.email);
  await page.goto("/clipper/new?mode=captions");
  await page.getByRole("tab", { name: "Upload" }).click();
  await page.getByTestId("file-input-source").setInputFiles(PODCAST);
  await expect(page.getByText("Ready: podcast.mp4")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("mode-captions")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("aspect-1:1").click();
  await expect(page.getByTestId("aspect-1:1")).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("Translate captions to").click();
  await page.getByRole("option", { name: "Spanish" }).click();
  await page.getByTestId("remove-silence").click();
  await expect(page.getByTestId("quote")).toContainText("80 tokens"); // captions 40 + translation 30 + jump cuts 10
  await page.getByTestId("create-clips").click();

  await expect(page).toHaveURL(/\/clipper\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("clip-status")).toHaveText("ready", { timeout: 480_000 });
  await expect(page.getByTestId("clip-frame")).toHaveAttribute("data-aspect", "1:1");
  await expect(page.getByTestId("project-summary")).toContainText("captions in es");
  await expect(page.getByTestId("caption-files")).toContainText("(es)");
});
