import { defineConfig, devices } from "@playwright/test";

/**
 * Checks the static (GitHub Pages) build. Build it first:
 *   STATIC_EXPORT=1 PAGES_BASE_PATH=/ClipperAI-By-Maitreya npx next build
 *   npx playwright test -c playwright.static.config.ts
 */
const ROOT = `${__dirname}/..`;
export const BASE = "/ClipperAI-By-Maitreya";

export default defineConfig({
  testDir: "./e2e-static",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: `http://localhost:3000${BASE}/`, trace: "off", screenshot: "only-on-failure", ...devices["Desktop Chrome"] },
  webServer: [
    {
      command: `${ROOT}/.venv/bin/uvicorn app.main:app --port 8000`,
      cwd: `${ROOT}/api`,
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      env: { PYTHONPATH: `${ROOT}/api`, OWNER_EMAIL: "e2e-owner@example.com" },
    },
    { command: `node scripts/pages-preview.mjs ${BASE} 3000`, url: `http://localhost:3000${BASE}/login/`, reuseExistingServer: false },
  ],
});
