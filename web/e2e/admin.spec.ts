import { expect, test } from "@playwright/test";
import { createMember, ensureOwner, login, rest } from "./helpers";

test("members can't open the admin panel", async ({ page }) => {
  const a = await createMember("member");
  await login(page, a.email);
  await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0);
  await page.goto("/admin");
  await expect(page.getByText("Admins only")).toBeVisible();
});

test("owner: overview, manage a user (plan, team, tokens, suspend, admin), requests, announcements, plans, health", async ({ page, browser }) => {
  test.setTimeout(180_000);
  const owner = await ensureOwner();
  const u = await createMember("member");
  await login(page, owner.email);
  await page.getByRole("link", { name: "Admin" }).first().click();
  await expect(page.getByTestId("stat-users")).toBeVisible();
  await expect(page.getByText("Owner & founder")).toBeVisible();

  // Find the user and manage them.
  await page.getByRole("link", { name: "Users" }).click();
  await page.getByLabel("Search users").fill(u.email);
  await expect(page.getByTestId("users-table").locator("tbody tr")).toHaveCount(1);
  await page.getByTestId("users-table").getByRole("link").first().click();
  await expect(page.getByTestId("user-name")).toBeVisible();

  await page.getByLabel("User plan").click();
  await page.getByRole("option", { name: "Pro" }).click();
  await expect(page.getByText("Plan changed to pro")).toBeVisible();

  await page.getByLabel("Token amount").fill("500");
  await page.getByLabel("Token note").fill("Welcome gift");
  await page.getByTestId("grant-tokens").click();
  await expect(page.getByText("Gave 500 tokens")).toBeVisible();
  await expect(page.getByTestId("user-tokens")).toContainText("5,500"); // Pro daily 5,000 + 500 bonus

  await page.getByLabel("User team").click();
  await page.getByRole("option", { name: "Content creator team (free)" }).click();
  await expect(page.getByText("Added to the creator team")).toBeVisible();
  await expect(page.getByTestId("user-tokens")).toHaveText(/∞/);

  await page.getByLabel("Suspend reason").fill("Testing");
  await page.getByTestId("suspend").click();
  await expect(page.getByTestId("user-status")).toHaveText("suspended");
  await page.getByTestId("reactivate").click();
  await expect(page.getByTestId("user-status")).toHaveText("active");

  await page.getByTestId("toggle-admin").click();
  await expect(page.getByText("Now an admin")).toBeVisible();
  await page.getByTestId("toggle-admin").click();
  await expect(page.getByText("Admin removed")).toBeVisible();

  // The user got a notification for the gift.
  const notes = await (await rest(`notifications?user_id=eq.${u.id}&select=title`)).json();
  expect(notes.map((n: { title: string }) => n.title)).toContain("You received 500 bonus tokens");

  // Approve an upgrade request.
  const v = await createMember("member");
  await rest("upgrade_requests", "POST", [{ user_id: v.id, plan_id: "business", note: "Agency account" }]);
  await page.goto("/admin/requests");
  const req = page.getByTestId("upgrade-request").filter({ hasText: "Agency account" });
  await req.getByLabel("Reply").fill("Welcome aboard");
  await req.getByTestId("approve").click();
  await expect(page.getByText(/is on Business now/)).toBeVisible();
  const [member] = await (await rest(`members?user_id=eq.${v.id}&select=plan_id`)).json();
  expect(member.plan_id).toBe("business");

  // Announcement shows on users' Home.
  const text = `E2E announcement ${Date.now()}`;
  await page.goto("/admin/announcements");
  await page.getByLabel("Announcement").fill(text);
  await page.getByTestId("post-announcement").click();
  await expect(page.getByText("Announcement is live")).toBeVisible();
  const ctx = await browser.newContext();
  const p2 = await ctx.newPage();
  await login(p2, v.email);
  await expect(p2.getByText(text)).toBeVisible();
  await ctx.close();
  await page.getByText(text).locator("..").locator("..").getByRole("button", { name: "End" }).click();

  // Plans: price change shows on the public pricing page; then restore.
  await page.goto("/admin/plans");
  const pro = page.getByTestId("admin-plan-pro");
  await pro.getByLabel("Pro price").fill("21");
  await page.getByTestId("save-plan-pro").click();
  await expect(page.getByText("Pro saved")).toBeVisible();
  await page.goto("/pricing");
  await expect(page.getByTestId("plan-pro")).toContainText("$21");
  await page.goto("/admin/plans");
  await page.getByTestId("admin-plan-pro").getByLabel("Pro price").fill("19");
  await page.getByTestId("save-plan-pro").click();
  await expect(page.getByText("Pro saved")).toBeVisible();

  await page.goto("/admin/jobs");
  await expect(page.getByTestId("jobs-table")).toBeVisible();
  await page.goto("/admin/audit");
  await expect(page.getByTestId("audit-table")).toContainText("tokens.grant");
  await page.goto("/admin/health");
  await expect(page.getByTestId("health")).toContainText("Database");
});
