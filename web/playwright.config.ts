import { defineConfig, devices } from "@playwright/test";

const ROOT = `${__dirname}/..`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  globalSetup: "./e2e/global-setup.ts",
  use: { baseURL: "http://localhost:3000", trace: "off", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, grep: /@mobile/ },
  ],
  webServer: [
    {
      command: `${ROOT}/.venv/bin/uvicorn app.main:app --port 8000`,
      cwd: `${ROOT}/api`,
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      env: { PYTHONPATH: `${ROOT}/api`, OWNER_EMAIL: "e2e-owner@example.com" }, // test owner, never the real one
    },
    { command: "npx next start -p 3000", url: "http://localhost:3000/login", reuseExistingServer: true },
  ],
});
