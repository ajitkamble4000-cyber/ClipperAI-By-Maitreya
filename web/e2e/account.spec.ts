import { expect, test } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createMember, login, rest } from "./helpers";

// A tiny valid PNG (1x1, red) for the brand-kit logo upload.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==",
  "base64",
);

test("visitors: landing, pricing, sign up and land on Home with 1,000 tokens", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/welcome$/);
  await expect(page.getByRole("heading", { level: 1, name: /Paste any link/ })).toBeVisible();
  await page.getByRole("link", { name: "Pricing" }).first().click();
  await expect(page.getByTestId("plan-free")).toBeVisible();
  await expect(page.getByTestId("plan-pro")).toContainText("5,000 tokens every day");
  await expect(page.getByTestId("plan-business")).toContainText("Batch mode");
  await expect(page.getByText("What things cost")).toBeVisible();

  await page.goto("/signup");
  const email = `e2e-signup-${Date.now()}@example.com`;
  await page.getByLabel("Your name").fill("Riya Sharma");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("a-strong-password");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
  await expect(page.getByText("Welcome back, Riya.")).toBeVisible();
  await expect(page.getByTestId("wallet-card")).toContainText("1,000");
  await expect(page.getByTestId("checklist")).toContainText("Getting started · 0/3");

  // Quick paste from Home goes to the maker with the link filled in.
  await page.getByTestId("quick-link").fill("https://www.youtube.com/watch?v=abc123");
  await page.getByTestId("quick-go").click();
  await expect(page).toHaveURL(/\/clipper\/new\?.*url=/);
  await expect(page.getByLabel("Video link")).toHaveValue("https://www.youtube.com/watch?v=abc123");
});

test("notifications bell, upgrade request, token history", async ({ page }) => {
  const a = await createMember("member");
  await login(page, a.email);
  await expect(page.getByTestId("bell").first()).toBeVisible();
  await rest("notifications", "POST", [{ user_id: a.id, kind: "success", title: "Your clips are ready", body: "3 clips", link: "/clipper" }]);
  await expect(page.getByTestId("bell-count").first()).toHaveText("1", { timeout: 15_000 }); // live, no reload
  await page.getByTestId("bell").first().click();
  await expect(page.getByRole("dialog", { name: "Notifications" })).toContainText("Your clips are ready");
  await page.getByRole("button", { name: "Mark all read" }).click();
  await expect(page.getByTestId("bell-count")).toHaveCount(0);

  await page.goto("/pricing");
  await page.getByTestId("upgrade-pro").click();
  await page.getByLabel("Note").fill("Posting daily");
  await page.getByTestId("send-request").click();
  await expect(page.getByText("Request sent").first()).toBeVisible();
  await expect(page.getByTestId("plan-free").getByTestId("current-plan")).toBeVisible();
  await page.goto("/account");
  await expect(page.getByTestId("account-plan")).toHaveText("Free");
  await expect(page.getByTestId("pending-request")).toContainText("You asked for Pro");

  await page.goto("/account/tokens");
  await expect(page.getByTestId("tokens-total")).toHaveText("1,000");
  await expect(page.getByTestId("ledger")).toContainText("Daily refill");
});

test("pro: brand kit with logo, and a public share link anyone can open", async ({ page, browser }) => {
  const a = await createMember("member", undefined, { plan_id: "pro" });
  await login(page, a.email);
  await page.goto("/account/brand");
  const logo = join(tmpdir(), `logo-${Date.now()}.png`);
  writeFileSync(logo, PNG);
  await page.getByTestId("file-input-image").setInputFiles(logo);
  await expect(page.getByTestId("logo-preview")).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Handle").fill("@riyamakes");
  await page.getByTestId("save-brand").click();
  await expect(page.getByText("Brand kit saved")).toBeVisible();
  await expect(page.getByTestId("brand-preview")).toContainText("@riyamakes");

  // A finished clip to share (set up directly; rendering is covered by the clipper tests).
  const [proj] = await (await rest("projects", "POST", [{ type: "clip", title: "Share me", created_by: a.id, status: "ready" }])).json();
  await rest("clips", "POST", [
    {
      project_id: proj.id, idx: 1, start_s: 0, end_s: 10, title: "My shared clip", status: "ready",
      video_key: `projects/${proj.id}/clips/x/v.mp4`, filename: "01-my-shared-clip.mp4", duration_s: 10,
    },
  ]);
  await page.goto(`/clipper/${proj.id}`);
  await page.getByTestId("share-clip").click();
  const toast = page.getByText(/\/s\/[A-Za-z0-9_-]{16,}/);
  await expect(toast).toBeVisible();
  const url = (await toast.textContent())!.match(/https?:\/\/\S+\/s\/[A-Za-z0-9_-]+/)![0];

  const anon = await browser.newContext();
  const p2 = await anon.newPage();
  await p2.goto(url);
  await expect(p2.getByTestId("shared-title")).toHaveText("My shared clip");
  await expect(p2.getByTestId("shared-video")).toBeAttached();
  await anon.close();

  await page.goto("/account");
  await expect(page.getByText("My shared clip")).toBeVisible();
  await page.getByRole("button", { name: "Turn off" }).click();
  const p3 = await (await browser.newContext()).newPage();
  await p3.goto(url);
  await expect(p3.getByText("This link isn't available")).toBeVisible();
});
