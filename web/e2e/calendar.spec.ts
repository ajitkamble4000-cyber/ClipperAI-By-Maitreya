import { expect, test } from "@playwright/test";
import { createMember, login, rest } from "./helpers";

test("schedule a clip, see it on the calendar, mark it posted, subscribe", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const a = await createMember("member");
  const [proj] = await (await rest("projects", "POST", [{ type: "clip", title: "Plan me", created_by: a.id, status: "ready" }])).json();
  await rest("clips", "POST", [
    { project_id: proj.id, idx: 1, start_s: 0, end_s: 10, title: "Scheduled clip", status: "ready",
      video_key: `projects/${proj.id}/clips/x/v.mp4`, filename: "01-scheduled.mp4", duration_s: 10 },
  ]);
  await login(page, a.email);
  await page.goto(`/clipper/${proj.id}`);
  await page.getByTestId("schedule").click();
  await page.getByLabel("Platform").click();
  await page.getByRole("option", { name: "TikTok" }).click();
  await expect(page.getByLabel("Post text")).toHaveValue(/Scheduled clip/);
  await page.getByTestId("save-schedule").click();
  await expect(page.getByText("Added to your calendar")).toBeVisible();

  await page.goto("/calendar");
  await expect(page.getByTestId("upcoming").first()).toContainText("Scheduled clip");
  await expect(page.getByTestId("cal-item").filter({ hasText: "Scheduled clip" })).toHaveCount(1);
  await page.getByTestId("upcoming").first().click();
  await page.getByLabel("Post link").fill("https://www.tiktok.com/@me/video/123");
  await page.getByTestId("mark-posted").click();
  await expect(page.getByText("Marked as posted")).toBeVisible();
  await expect(page.getByTestId("upcoming")).toHaveCount(0);

  await page.getByTestId("subscribe").click();
  await expect(page.getByText("Calendar link copied")).toBeVisible();
  const url = await page.evaluate(() => navigator.clipboard.readText());
  expect(url).toMatch(/\/public\/calendar\/[\w-]+\.ics$/);
  const ics = await (await fetch(url)).text();
  expect(ics).toContain("SUMMARY:✓ Post on TikTok: Scheduled clip");
});
