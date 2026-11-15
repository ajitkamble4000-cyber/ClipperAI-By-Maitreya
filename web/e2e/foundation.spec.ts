import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomBytes } from "node:crypto";
import { expect, test } from "@playwright/test";
import { createMember, latestEmailLink, login } from "./helpers";

test("unauthenticated users are sent to login", async ({ page }) => {
  await page.goto("/settings");
  await expect(page).toHaveURL(/\/login\?next=%2Fsettings/);
});

test("admin invites a teammate who joins via the email link", async ({ page, browser }) => {
  const a = await createMember("admin");
  await login(page, a.email);
  await page.goto("/settings?tab=members");
  const invitee = `invitee-${Date.now()}@example.com`;
  await page.getByLabel("Invite email").fill(invitee);
  await page.getByRole("button", { name: "Invite" }).click();
  await expect(page.getByText(`Invite sent to ${invitee}`)).toBeVisible();

  const link = await latestEmailLink(invitee);
  const ctx = await browser.newContext();
  const p2 = await ctx.newPage();
  await p2.goto(link);
  await expect(p2).toHaveURL(/\/auth\/accept/);
  await p2.getByLabel("Your name").fill("New Teammate");
  await p2.getByLabel("Password").fill("brand-new-password");
  await p2.getByRole("button", { name: "Continue" }).click();
  await expect(p2.getByRole("heading", { name: "Home" })).toBeVisible();
  await p2.goto("/settings?tab=members");
  await expect(p2.getByText("New Teammate (you)")).toBeVisible();
  // Members cannot invite.
  await expect(p2.getByLabel("Invite email")).toHaveCount(0);
  await ctx.close();
});

test("dummy job progress is live in two browsers", async ({ page, browser }) => {
  const a = await createMember("member");
  await login(page, a.email);
  await page.goto("/settings?tab=diagnostics");
  await page.getByTestId("run-dummy").click();
  await expect(page).toHaveURL(/job=/);
  const url = page.url();

  // Same account on a second device: jobs are private, but live everywhere you're signed in.
  const ctx = await browser.newContext();
  const p2 = await ctx.newPage();
  await login(p2, a.email);
  await p2.goto(url.replace("http://localhost:3000", ""));

  const seen = new Set<string>();
  for (let i = 0; i < 60; i++) {
    const t = await p2.getByTestId("job-percent").textContent().catch(() => null);
    if (t) seen.add(t);
    if ((await p2.getByTestId("job-progress").getAttribute("data-status").catch(() => null)) === "succeeded") break;
    await p2.waitForTimeout(250);
  }
  await expect(page.getByTestId("job-progress")).toHaveAttribute("data-status", "succeeded");
  await expect(p2.getByTestId("job-progress")).toHaveAttribute("data-status", "succeeded");
  expect(seen.size, `second browser saw ${[...seen].join(",")}`).toBeGreaterThanOrEqual(3);

  // Survives a refresh.
  await p2.reload();
  await expect(p2.getByTestId("job-progress")).toHaveAttribute("data-status", "succeeded");
  await ctx.close();
});

test("upload resumes after a page refresh without re-sending finished parts", async ({ page }) => {
  const a = await createMember("member");
  await login(page, a.email);
  const file = join(tmpdir(), `e2e-${Date.now()}.mp4`);
  writeFileSync(file, randomBytes(8 * 1024 * 1024 * 5 + 777)); // 6 parts
  await page.goto("/settings?tab=diagnostics");

  // Let parts 1-2 reach storage; block the rest (simulates the tab closing mid-upload).
  const stored = new Set<number>();
  await page.route("http://127.0.0.1:9090/**", async (route) => {
    const n = Number(new URL(route.request().url()).searchParams.get("partNumber"));
    if (route.request().method() === "PUT" && n > 2) return route.abort();
    await route.continue();
    if (n) stored.add(n);
  });
  await page.getByTestId("file-input-source").setInputFiles(file);
  await expect.poll(() => stored.size).toBe(2);
  await page.reload();
  await page.unroute("http://127.0.0.1:9090/**");
  await expect(page.getByText(/Unfinished upload: e2e-.*\.mp4/)).toBeVisible();

  const parts: number[] = [];
  page.on("request", (r) => {
    if (r.method() === "PUT" && r.url().startsWith("http://127.0.0.1:9090")) parts.push(Number(new URL(r.url()).searchParams.get("partNumber")));
  });
  await page.getByTestId("file-input-source").setInputFiles(file);
  await expect(page.getByTestId("upload-done")).toBeVisible();
  expect([...new Set(parts)].sort()).toEqual([3, 4, 5, 6]);
});

test("library and nav work on a phone @mobile", async ({ page }) => {
  const a = await createMember("member");
  await login(page, a.email);
  await expect(page.getByRole("link", { name: "Account" }).last()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
});
