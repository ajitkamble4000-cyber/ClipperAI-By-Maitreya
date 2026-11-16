import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createMember, login, putObject, rest } from "./helpers";

test.skip(process.env.STUDIO_FAKE_GEMINI !== "1", "run with STUDIO_FAKE_GEMINI=1");

function video(seconds: number, color: string): Buffer {
  const out = join(tmpdir(), `e2e-${color}-${Date.now()}.mp4`);
  execFileSync("ffmpeg", [
    "-v", "error", "-y", "-f", "lavfi", "-i", `color=c=${color}:s=1080x1920:r=30:d=${seconds}`,
    "-f", "lavfi", "-i", `sine=f=330:r=48000:d=${seconds}`, "-t", String(seconds),
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out,
  ]);
  return readFileSync(out);
}

test("edit captions, export MP3, add music, make a compilation", async ({ page }) => {
  test.setTimeout(240_000);
  const a = await createMember("member", undefined, { plan_id: "pro" });
  const transcript = {
    language: "en", duration: 4,
    segments: [{ start: 0, end: 4, text: "Helo wrld", words: [{ text: "Helo", start: 0.3, end: 0.9, prob: 1 }, { text: "wrld", start: 1.0, end: 1.6, prob: 1 }] }],
  };
  const tkey = `cache/e2e/${Date.now()}.json`;
  await putObject(tkey, Buffer.from(JSON.stringify(transcript)), "application/json");
  const [proj] = await (await rest("projects", "POST", [
    { type: "clip", title: "Edit tools", created_by: a.id, status: "ready", meta: { transcript_key: tkey, options: { content_type: "podcast" } } },
  ])).json();
  const rows = [];
  for (const [i, color] of [[1, "navy"], [2, "maroon"]] as const) {
    const base = `projects/${proj.id}/clips/c${i}/base.mp4`;
    const vid = video(4, color);
    await putObject(base, vid, "video/mp4");
    await putObject(`projects/${proj.id}/clips/c${i}/final.mp4`, vid, "video/mp4");
    const words = `projects/${proj.id}/clips/c${i}/words.json`;
    await putObject(words, Buffer.from(JSON.stringify([{ text: "Helo", start: 0.3, end: 0.9 }, { text: "wrld", start: 1.0, end: 1.6 }])), "application/json");
    rows.push({
      project_id: proj.id, idx: i, start_s: 0, end_s: 4, title: `Clip ${i}`, status: "ready", base_key: base,
      video_key: `projects/${proj.id}/clips/c${i}/final.mp4`, words_key: words, filename: `0${i}-clip.mp4`, duration_s: 4,
      caption_style: { preset: "minimal" }, reframe: "center",
    });
  }
  await rest("clips", "POST", rows);
  await login(page, a.email);
  await page.goto(`/clipper/${proj.id}`);
  const first = page.getByTestId("clip-card").first();

  // Fix a typo in the captions.
  await first.getByTestId("edit-captions").click();
  await page.getByLabel("Caption line 1").fill("Hello world");
  await page.getByTestId("save-captions").click();
  await expect(page.getByText("Captions saved")).toBeVisible();
  await expect(first.getByTestId("clip-status")).toHaveText("ready", { timeout: 120_000 });
  await first.getByTestId("edit-captions").click();
  await expect(page.getByLabel("Caption line 1")).toHaveValue("Hello world");
  await page.keyboard.press("Escape");

  // MP3 export downloads a file.
  const dl = page.waitForEvent("download", { timeout: 60_000 });
  await first.getByTestId("export-mp3").click();
  expect((await dl).suggestedFilename()).toMatch(/\.mp3$/);

  // Background music re-renders the clip.
  await first.getByLabel("Background music").click();
  await page.getByRole("option", { name: "Calm" }).click();
  await expect(page.getByText("Adding music")).toBeVisible();
  await expect(first.getByTestId("clip-status")).toHaveText("ready", { timeout: 120_000 });

  // Join both clips into one video.
  await page.getByTestId("compilation").click();
  const dl2 = page.waitForEvent("download", { timeout: 120_000 });
  await page.getByTestId("make-compilation").click();
  expect((await dl2).suggestedFilename()).toMatch(/\.mp4$/);
});
