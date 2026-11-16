import { expect, test } from "@playwright/test";
import { createMember, login, putObject, rest } from "./helpers";

test.skip(process.env.STUDIO_FAKE_GEMINI !== "1", "run with STUDIO_FAKE_GEMINI=1");

test("write a video up (summary, chapters, posts) and search what was said", async ({ page }) => {
  const a = await createMember("member");
  const word = `aardvark${Date.now().toString(36)}`;
  const transcript = {
    language: "en", duration: 90,
    segments: [
      { start: 0, end: 10, text: "Welcome to the show", words: [] },
      { start: 40, end: 48, text: `Today we talk about the ${word} in detail`, words: [] },
    ],
  };
  const tkey = `cache/e2e/${Date.now()}-rp.json`;
  await putObject(tkey, Buffer.from(JSON.stringify(transcript)), "application/json");
  const [proj] = await (await rest("projects", "POST", [
    { type: "clip", title: "Animal talk", created_by: a.id, status: "ready", meta: { transcript_key: tkey } },
  ])).json();
  await rest("project_transcripts", "POST", [
    { project_id: proj.id, language: "en", text: transcript.segments.map((s) => s.text).join(" "), segments: transcript.segments },
  ]);

  await login(page, a.email);
  await page.goto(`/clipper/${proj.id}`);
  await page.getByTestId("write-it-up").click();
  await expect(page.getByTestId("rp-summary")).toContainText("A short talk about getting started.", { timeout: 60_000 });
  await expect(page.getByTestId("rp-chapters")).toContainText("0:00 Intro");
  await expect(page.getByText("1/ Getting started is the hardest part.")).toBeVisible();
  const dl = page.waitForEvent("download");
  await page.getByRole("button", { name: ".md" }).click();
  expect((await dl).suggestedFilename()).toBe("animal-talk-writeup.md");

  await page.goto("/library");
  await page.getByLabel("Search what was said").fill(word);
  const hit = page.getByTestId("transcript-hit").first();
  await expect(hit).toContainText("Animal talk");
  await expect(hit).toContainText("at 0:40");
  await hit.click();
  await expect(page).toHaveURL(new RegExp(`/clipper/${proj.id}$`));
});
