import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { createMember, login, rest } from "./helpers";

async function seed(uid: string) {
  const [proj] = await (await rest("projects", "POST", [{ type: "clip", title: "Stats source", created_by: uid, status: "ready" }])).json();
  await rest("sources", "POST", [{ project_id: proj.id, kind: "url", url: "https://example.com/v", duration_s: 900 }]);
  await rest("clips", "POST", [
    { project_id: proj.id, idx: 1, start_s: 0, end_s: 40, title: "Top moment", status: "ready", virality_score: 91, duration_s: 40 },
    { project_id: proj.id, idx: 2, start_s: 50, end_s: 70, title: "Second best", status: "ready", virality_score: 64, duration_s: 20 },
  ]);
  const now = new Date().toISOString();
  const [job] = await (
    await rest("jobs", "POST", [{ project_id: proj.id, kind: "clip", status: "succeeded", created_by: uid, finished_at: now, tokens_charged: 120 }])
  ).json();
  await rest("token_ledger", "POST", [
    { user_id: uid, delta: -120, bucket: "daily", reason: "charge", action: "clip", job_id: job.id,
      meta: { from_daily: 120, from_bonus: 0 } }, // what a real charge records
  ]);
  return { proj, job };
}

test("personal stats: tiles, daily chart with tooltip and table, tokens by feature, best clips", async ({ page }) => {
  const a = await createMember("member");
  await seed(a.id);
  await login(page, a.email);
  await page.goto("/account");
  await page.getByRole("link", { name: /Your stats/ }).click();
  await expect(page.getByRole("heading", { name: "Your stats" })).toBeVisible();

  await expect(page.getByTestId("stat-clips")).toContainText("2");
  await expect(page.getByTestId("stat-clips")).toContainText("1 min of Shorts");
  await expect(page.getByTestId("stat-minutes")).toContainText("15 min");
  await expect(page.getByTestId("stat-tokens")).toContainText("120");
  await expect(page.getByTestId("stat-streak")).toContainText("1");
  await expect(page.getByTestId("by-feature")).toContainText("Clips");
  await expect(page.getByTestId("best-clips").getByRole("link").first()).toContainText("Top moment");

  await expect(page.getByTestId("day-bar")).toHaveCount(30);
  await page.getByTestId("day-bar").last().hover();
  await expect(page.getByTestId("chart-tooltip")).toContainText("120 tokens · 2 clips · 1 job");
  await page.getByRole("group", { name: "Chart metric" }).getByRole("button", { name: "Clips" }).click();
  await expect(page.getByText("Clips made per day")).toBeVisible();
  await page.getByRole("group", { name: "Time range" }).getByRole("button", { name: "7 days" }).click();
  await expect(page.getByTestId("day-bar")).toHaveCount(7);
  await page.getByText("View as table").click();
  await expect(page.getByRole("row")).toHaveCount(8); // header + 7 days

  await page.getByTestId("best-clips").getByRole("link").first().click();
  await expect(page.getByTestId("project-title")).toHaveText("Stats source");
});

test("admin refunds a finished job and exports users as CSV", async ({ page }) => {
  const u = await createMember("member");
  const { job } = await seed(u.id);
  const admin = await createMember("admin");
  await login(page, admin.email);

  await page.goto("/admin/jobs");
  await page.getByLabel("Search jobs").fill(u.email);
  const refund = page.getByTestId("refund-job");
  await expect(refund).toHaveCount(1);
  page.once("dialog", (d) => d.accept("The captions were out of sync"));
  await refund.click();
  await expect(page.getByText("120 tokens refunded")).toBeVisible();
  await expect(page.getByTestId("refund-job")).toHaveCount(0); // nothing left to refund
  const [note] = await (await rest(`notifications?user_id=eq.${u.id}&order=created_at.desc&limit=1&select=title,body`)).json();
  expect(note.title).toBe("120 tokens refunded");
  expect(note.body).toContain("The captions were out of sync");
  const [j] = await (await rest(`jobs?id=eq.${job.id}&select=tokens_charged`)).json();
  expect(j.tokens_charged).toBe(0);

  await page.goto("/admin/users");
  await page.getByLabel("Search users").fill(u.email);
  await expect(page.getByTestId("users-table")).toContainText(u.email);
  const download = page.waitForEvent("download");
  await page.getByTestId("export-users").click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^users-\d{4}-\d{2}-\d{2}\.csv$/);
  const csv = readFileSync((await file.path())!, "utf8");
  const [header, row, extra] = csv.trim().split(/\r?\n/);
  expect(header).toBe("email,name,role,plan,status,team,joined,last_seen,daily_tokens,bonus_tokens,lifetime_spent,projects,jobs_30d");
  expect(row).toContain(u.email);
  expect(extra).toBeUndefined(); // the search filter applies to the export
});
