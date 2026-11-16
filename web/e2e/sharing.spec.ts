import { expect, test } from "@playwright/test";
import { createMember, login, rest } from "./helpers";

test("owner shares a project; the viewer finds it in Library and sees it read-only", async ({ page, browser }) => {
  const owner = await createMember("member", undefined, { plan_id: "pro" });
  const viewer = await createMember("member");
  const [proj] = await (await rest("projects", "POST", [{ type: "clip", title: "Team review cut", created_by: owner.id, status: "ready" }])).json();
  await rest("clips", "POST", [
    { project_id: proj.id, idx: 1, start_s: 0, end_s: 12, title: "Shared clip", status: "ready",
      video_key: `projects/${proj.id}/clips/x/v.mp4`, filename: "01-shared.mp4", duration_s: 12 },
  ]);

  // Owner invites by email
  await login(page, owner.email);
  await page.goto(`/clipper/${proj.id}`);
  await page.getByTestId("share").click();
  await expect(page.getByText("Only you can see this project.")).toBeVisible();
  await page.getByLabel("Email to share with").fill(viewer.email);
  await page.getByTestId("share-invite").click();
  await expect(page.getByText(`Shared with ${viewer.email}`)).toBeVisible();
  await expect(page.getByTestId("share-person")).toContainText(viewer.email);
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("share")).toContainText("Share (1)");

  // Viewer: notification, Library filter, read-only project
  const ctx = await browser.newContext();
  const vpage = await ctx.newPage();
  await login(vpage, viewer.email);
  await vpage.goto("/library");
  await vpage.getByLabel("Made by").click();
  await vpage.getByRole("option", { name: "Shared with me" }).click();
  await expect(vpage.getByTestId("library-grid").getByRole("link")).toHaveCount(1);
  await expect(vpage.getByTestId("shared-badge")).toHaveText(/view only/);
  await vpage.getByTestId("library-grid").getByRole("link").first().click();

  await expect(vpage.getByTestId("project-title")).toHaveText("Team review cut");
  await expect(vpage.getByTestId("view-only")).toBeVisible();
  await expect(vpage.getByTestId("share")).toContainText("view only");
  await expect(vpage.getByLabel(/^Title/)).toHaveAttribute("readonly", "");
  await expect(vpage.getByLabel("Change caption style")).toBeDisabled();
  await expect(vpage.getByTestId("edit-captions")).toBeDisabled();
  await expect(vpage.getByTestId("make-thumbnail")).toHaveCount(0);
  await expect(vpage.getByRole("button", { name: "Delete project" })).toHaveCount(0);

  // Owner upgrades them to editor; after a reload the viewer can edit
  await page.getByTestId("share").click();
  await page.getByLabel(`Access for ${viewer.email}`).click();
  await page.getByRole("option", { name: "Can edit" }).click();
  await expect.poll(async () => (await (await rest(`project_members?project_id=eq.${proj.id}&select=role`)).json())[0]?.role).toBe("editor");
  await vpage.reload();
  await expect(vpage.getByTestId("share")).toContainText("can edit");
  await expect(vpage.getByTestId("view-only")).toHaveCount(0);
  await expect(vpage.getByLabel(/^Title/)).not.toHaveAttribute("readonly", "");

  // Viewer leaves
  vpage.on("dialog", (d) => d.accept());
  await vpage.getByTestId("share").click();
  await vpage.getByRole("button", { name: "Leave project" }).click();
  await expect(vpage).toHaveURL(/\/library$/);
  await expect.poll(async () => (await (await rest(`project_members?project_id=eq.${proj.id}&select=role`)).json()).length).toBe(0);
  await ctx.close();
});
