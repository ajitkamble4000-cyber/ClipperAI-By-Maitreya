import { spawn } from "node:child_process";
import { resolve } from "node:path";

/** Start a Celery worker for the duration of the test run. */
export default async function globalSetup() {
  const root = resolve(__dirname, "../..");
  const worker = spawn(
    `${root}/.venv/bin/celery`,
    ["-A", "worker.celery_app", "worker", "-Q", "media,ai,poll", "--concurrency", "2", "--loglevel", "WARNING"],
    { cwd: root, env: { ...process.env, PYTHONPATH: `${root}/worker`, STUDIO_FAKE_GEMINI: process.env.STUDIO_FAKE_GEMINI ?? "" }, stdio: "inherit" },
  );
  await new Promise((r) => setTimeout(r, 4000));
  return async () => {
    worker.kill("SIGTERM");
  };
}
