import { expect, test } from "@playwright/test";
import { createMember, login, SUPABASE } from "./helpers";

const SERVICE =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU";
const H = { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, "Content-Type": "application/json", Prefer: "return=representation" };

async function seedStory(userId: string) {
  const p = await (await fetch(`${SUPABASE}/rest/v1/projects`, { method: "POST", headers: H, body: JSON.stringify({ type: "story", title: "Seeded story", created_by: userId, status: "storyboard" }) })).json();
  const pid = p[0].id;
  await fetch(`${SUPABASE}/rest/v1/stories`, { method: "POST", headers: H, body: JSON.stringify({ project_id: pid, idea: "What if the moon disappeared", title: "What if the moon vanished?", hook_text: "NO MORE MOON", hashtags: ["#space"] }) });
  const scenes = ["The moon is gone.", "Tides collapse overnight.", "Nights turn pitch black."].map((n, i) => ({
    project_id: pid, idx: i, narration: n, image_prompt: `prompt ${i}`, camera_motion: "zoom-in", duration_estimate: 3,
  }));
  await fetch(`${SUPABASE}/rest/v1/scenes`, { method: "POST", headers: H, body: JSON.stringify(scenes) });
  return pid as string;
}

test("new story form creates a story; no Gemini key shows a clear error", async ({ page }) => {
  test.skip(process.env.STUDIO_FAKE_GEMINI === "1", "needs the real (unconfigured) Gemini client");
  const a = await createMember("member");
  await login(page, a.email);
  await page.goto("/story/new");
  await page.getByTestId("genre-scary").click();
  await page.getByLabel("Story idea").fill("Scary story: the last bus at midnight");
  await page.getByTestId("write-script").click();
  await expect(page).toHaveURL(/\/story\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("job-error")).toContainText(/Gemini API key|Settings/, { timeout: 60_000 });
});

test("storyboard: autosave, reorder, add, delete, live collaboration", async ({ page, browser }) => {
  // Two Staff-team members: the team library is shared, so they can co-edit.
  const a = await createMember("member", undefined, { team: "staff", plan_id: "team" });
  const pid = await seedStory(a.id);
  await login(page, a.email);
  await page.goto(`/story/${pid}`);
  await expect(page.getByTestId("scene-card")).toHaveCount(3);

  // Teammate opens the same story.
  const b = await createMember("member", undefined, { team: "staff", plan_id: "team" });
  const ctx = await browser.newContext();
  const p2 = await ctx.newPage();
  await login(p2, b.email);
  await p2.goto(`/story/${pid}`);
  await expect(page.getByTestId("presence")).toContainText("E2E member");

  // Autosave narration; teammate sees it live.
  const first = page.getByTestId("scene-card").first().getByLabel("Narration");
  await first.fill("The moon vanished at 3:14 AM.");
  await expect(page.getByTestId("save-state")).toContainText("Saved");
  await expect(p2.getByTestId("scene-card").first().getByLabel("Narration")).toHaveValue("The moon vanished at 3:14 AM.", { timeout: 15_000 });

  // Reorder: move scene 3 up.
  await page.getByTestId("scene-card").nth(2).getByRole("button", { name: "Move scene up" }).click();
  await expect(page.getByTestId("scene-card").nth(1).getByLabel("Narration")).toHaveValue("Nights turn pitch black.");
  // Add and delete.
  await page.getByTestId("add-scene").click();
  await expect(page.getByTestId("scene-card")).toHaveCount(4);
  await page.getByTestId("scene-card").nth(3).getByLabel("Narration").fill("A brand new ending.");
  await expect(page.getByTestId("save-state")).toContainText("Saved");
  await page.getByTestId("scene-card").first().getByRole("button", { name: "Delete scene" }).click();
  await expect(page.getByTestId("scene-card")).toHaveCount(3);

  // Everything persisted.
  await page.reload();
  await expect(page.getByTestId("scene-card")).toHaveCount(3);
  const narr = await page.getByTestId("scene-card").getByLabel("Narration").evaluateAll((els) => els.map((e) => (e as HTMLTextAreaElement).value));
  expect(narr).toEqual(["Nights turn pitch black.", "Tides collapse overnight.", "A brand new ending."]);
  await ctx.close();
});
