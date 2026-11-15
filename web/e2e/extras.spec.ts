import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createMember, login, putObject, rest } from "./helpers";

// Needs the worker started with STUDIO_FAKE_GEMINI=1 (offline fake AI).
test.skip(process.env.STUDIO_FAKE_GEMINI !== "1", "run with STUDIO_FAKE_GEMINI=1");

const FRAME = readFileSync(resolve(__dirname, "fixtures-frame.jpg"));

test("templates: built-ins for everyone, saving your own is Pro", async ({ page }) => {
  const free = await createMember("member");
  await login(page, free.email);
  await page.goto("/clipper/new");
  await page.getByTestId("template-chip").filter({ hasText: "TikTok captions" }).click();
  await expect(page.getByTestId("mode-captions")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("template-chip").filter({ hasText: "YouTube 16:9 (Pro)" }).click();
  await expect(page.getByText("Square / 4:5 / 16:9 output is part of Pro")).toBeVisible(); // locked parts are skipped
  await expect(page.getByTestId("aspect-9:16")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("new-template").click();
  await expect(page.getByText("Templates is part of Pro")).toBeVisible();

  const pro = await createMember("member", undefined, { plan_id: "pro" });
  await page.context().clearCookies();
  await login(page, pro.email);
  await page.goto("/clipper/new");
  await page.getByTestId("aspect-1:1").click();
  await page.getByTestId("new-template").click();
  await page.getByLabel("Template name").fill("My square preset");
  await page.getByTestId("save-template").click();
  await expect(page.getByTestId("template-chip").filter({ hasText: "My square preset" })).toBeVisible();
  await page.reload();
  await page.getByTestId("template-chip").filter({ hasText: "My square preset" }).click();
  await expect(page.getByTestId("aspect-1:1")).toHaveAttribute("aria-pressed", "true");
});

test("pro: designed thumbnail and title ideas on a clip", async ({ page }) => {
  const a = await createMember("member", undefined, { plan_id: "pro" });
  const [proj] = await (await rest("projects", "POST", [{ type: "clip", title: "Extras", created_by: a.id, status: "ready" }])).json();
  const thumb = `projects/${proj.id}/clips/x/thumb.jpg`;
  await putObject(thumb, FRAME, "image/jpeg");
  await rest("clips", "POST", [
    { project_id: proj.id, idx: 1, start_s: 0, end_s: 10, title: "Original title", hook_text: "WATCH THIS", status: "ready",
      thumb_key: thumb, video_key: `projects/${proj.id}/clips/x/v.mp4`, filename: "01-original.mp4", duration_s: 10 },
  ]);
  await login(page, a.email);
  await page.goto(`/clipper/${proj.id}`);
  await page.getByTestId("make-thumbnail").click();
  await expect(page.getByTestId("cover-preview")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("button", { name: "YouTube 16:9" })).toBeVisible();
  await page.getByTestId("make-ideas").click();
  await expect(page.getByTestId("idea-title")).toHaveCount(5, { timeout: 60_000 });
  await page.getByTestId("idea-title").first().click();
  await expect(page.getByLabel(/Title \(/)).toHaveValue("I tried this for 30 days");
});

test("business: many story topics at once; new genres", async ({ page }) => {
  const a = await createMember("member", undefined, { plan_id: "business" });
  await login(page, a.email);
  await page.goto("/story/new");
  await expect(page.getByTestId("genre-bedtime")).toBeVisible();
  await page.getByTestId("genre-facts").click();
  await page.getByTestId("story-batch-tab").click();
  const stamp = Date.now();
  await page.getByLabel("Story idea").fill(`Why do cats purr ${stamp}\nHow volcanoes form ${stamp}`);
  await page.getByTestId("write-script").click();
  await expect(page.getByText("Writing 2 scripts")).toBeVisible();
  await expect(page).toHaveURL(/\/story$/);
  await expect(page.getByText(`Why do cats purr ${stamp}`).or(page.getByText("What if you fell into a black hole?")).first()).toBeVisible();
  const rows = await (await rest(`projects?created_by=eq.${a.id}&type=eq.story&select=id`)).json();
  expect(rows.length).toBe(2);
});
