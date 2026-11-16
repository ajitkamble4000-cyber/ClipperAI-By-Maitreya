import { expect, test } from "@playwright/test";
import { createMember, ensureOwner, login, rest } from "./helpers";

test.afterAll(async () => {
  await rest("settings?id=eq.1", "PATCH", { signups_open: true, jobs_paused: false, maintenance_message: "" });
});

test("owner creates a promo code; a user redeems it for tokens; trials unlock a plan", async ({ page, browser }) => {
  const owner = await ensureOwner();
  await login(page, owner.email);
  await page.goto("/admin/promos");
  const code = `E2E${Date.now().toString(36).toUpperCase()}`;
  await page.getByLabel("New code").fill(code);
  await page.getByLabel("Code tokens").fill("750");
  await page.getByTestId("create-promo").click();
  await expect(page.getByTestId("promos-table")).toContainText(code);
  const trial = `${code}T`;
  await page.getByLabel("New code").fill(trial);
  await page.getByLabel("Code type").click();
  await page.getByRole("option", { name: "Plan trial" }).click();
  await page.getByTestId("create-promo").click();
  await expect(page.getByTestId("promos-table")).toContainText(trial);

  const u = await createMember("member");
  const ctx = await browser.newContext();
  const p2 = await ctx.newPage();
  await login(p2, u.email);
  await p2.goto("/account/tokens");
  await p2.getByLabel("Promo code").fill(code);
  await p2.getByTestId("redeem").click();
  await expect(p2.getByText("750 bonus tokens added")).toBeVisible();
  await expect(p2.getByTestId("ledger")).toContainText(`Promo code ${code}`);
  await p2.getByLabel("Promo code").fill(trial);
  await p2.getByTestId("redeem").click();
  await expect(p2.getByText("Pro unlocked for 7 days")).toBeVisible();
  await p2.goto("/account");
  await expect(p2.getByTestId("account-plan")).toHaveText("Pro");
  await expect(p2.getByTestId("trial-note")).toBeVisible();
  await ctx.close();
});

test("referral link: the friend sees the bonus note; site controls show a banner and close sign-ups", async ({ page, browser }) => {
  const a = await createMember("member");
  await login(page, a.email);
  await page.goto("/account/tokens");
  const link = await page.getByTestId("referral-link").inputValue();
  expect(link).toMatch(/\/signup\?ref=[a-z0-9]+$/);

  const anon = await browser.newContext();
  const p2 = await anon.newPage();
  await p2.goto(link);
  await expect(p2.getByTestId("referral-note")).toContainText("you'll both get 500 bonus tokens");
  const email = `e2e-ref-${Date.now()}@example.com`;
  await p2.getByLabel("Your name").fill("Friend");
  await p2.getByLabel("Email").fill(email);
  await p2.getByLabel("Password").fill("a-strong-password");
  await p2.getByRole("button", { name: "Create account" }).click();
  await expect(p2.getByRole("heading", { name: "Home" })).toBeVisible();
  await anon.close();
  await page.reload();
  await expect(page.getByTestId("referral-card")).toContainText("1 joined");

  const owner = await ensureOwner();
  const o = await (await browser.newContext()).newPage();
  await login(o, owner.email);
  await o.goto("/admin/site");
  await o.getByLabel("Banner message").fill("Maintenance tonight at 11pm");
  await o.getByLabel("Open sign-ups").click();
  await o.getByTestId("save-site").click();
  await expect(o.getByText("Changes are live")).toBeVisible();

  const visitor = await (await browser.newContext()).newPage();
  await visitor.goto("/signup");
  await expect(visitor.getByTestId("site-banner")).toContainText("Maintenance tonight at 11pm");
  await expect(visitor.getByTestId("signups-closed")).toBeVisible();

  await o.getByLabel("Banner message").fill("");
  await o.getByLabel("Open sign-ups").click();
  await o.getByTestId("save-site").click();
  await expect(o.getByText("Changes are live")).toBeVisible();
});
