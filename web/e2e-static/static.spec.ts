import { expect, test } from "@playwright/test";
import { createMember, PASSWORD, rest } from "../e2e/helpers";

const BASE = "/ClipperAI-By-Maitreya";

test("static build on a sub-path: sign-in, id pages, forwarded links, share links, 404", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const a = await createMember("member", undefined, { plan_id: "pro" });
  const [proj] = await (await rest("projects", "POST", [{ type: "clip", title: "Static site project", created_by: a.id, status: "ready" }])).json();
  await rest("clips", "POST", [
    { project_id: proj.id, idx: 1, start_s: 0, end_s: 10, title: "Static clip", status: "ready",
      video_key: `projects/${proj.id}/clips/x/v.mp4`, filename: "01-static.mp4", duration_s: 10 },
  ]);

  // signed out: the home page sends visitors to the landing page
  await page.goto("./");
  await expect(page).toHaveURL(new RegExp(`${BASE}/welcome/$`));
  await expect(page.getByTestId("brand").first()).toContainText("ClipperAI");

  // a protected deep link asks to sign in, then comes back to it
  await page.goto(`${BASE}/clipper/${proj.id}`);
  await expect(page).toHaveURL(/\/login\/\?next=/);
  await page.getByLabel("Email").fill(a.email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("project-title")).toHaveText("Static site project");
  await expect(page).toHaveURL(new RegExp(`${BASE}/clipper/_/\\?id=${proj.id}`));

  // in-app links use the static form directly
  await page.goto("library/");
  await page.getByTestId("library-grid").getByRole("link", { name: /Static site project/ }).click();
  await expect(page).toHaveURL(new RegExp(`/clipper/_/\\?id=${proj.id}`));
  await expect(page.getByTestId("clip-card")).toHaveCount(1);

  // share link: copied with the base path, opens without an account
  await page.getByTestId("share-clip").click();
  await expect(page.getByText("Share link copied")).toBeVisible();
  const link = await page.evaluate(() => navigator.clipboard.readText());
  expect(link).toMatch(new RegExp(`^http://localhost:3000${BASE}/s/_/\\?id=[\\w-]+$`));
  const anon = await context.browser()!.newContext();
  const p2 = await anon.newPage();
  await p2.goto(link);
  await expect(p2.getByTestId("shared-title")).toHaveText("Static clip");
  // the old path form (as stored in notifications or older links) is forwarded too
  const token = new URL(link).searchParams.get("id");
  await p2.goto(`http://localhost:3000${BASE}/s/${token}`);
  await expect(p2.getByTestId("shared-title")).toHaveText("Static clip");
  await expect(p2).toHaveURL(new RegExp(`/s/_/\\?id=${token}`));
  await anon.close();

  // unknown pages show a real 404
  await page.goto(`${BASE}/no-such-page`);
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();

  // sign out returns to sign-in
  await page.goto("./");
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).first().click();
  await expect(page).toHaveURL(/\/login\/$/);
});
