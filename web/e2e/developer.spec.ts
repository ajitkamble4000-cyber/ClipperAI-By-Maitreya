import { expect, test } from "@playwright/test";
import { createHmac } from "node:crypto";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { createMember, login } from "./helpers";

test("business: API key works from code; a webhook test is delivered and signed", async ({ page }) => {
  const received: { headers: Record<string, string | string[] | undefined>; body: string }[] = [];
  const server = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      received.push({ headers: req.headers, body });
      res.writeHead(200).end("ok");
    });
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const port = (server.address() as AddressInfo).port;

  const a = await createMember("member", undefined, { plan_id: "business" });
  await login(page, a.email);
  await page.goto("/account/developer");
  await page.getByLabel("Key name").fill("My script");
  await page.getByTestId("create-key").click();
  const key = (await page.getByTestId("secret-value").textContent())!.trim();
  expect(key).toMatch(/^ss_live_/);
  await expect(page.getByTestId("api-key-row")).toContainText("My script");
  const me = await (await fetch("http://127.0.0.1:8000/me", { headers: { "X-API-Key": key } })).json();
  expect(me.user_id).toBe(a.id);

  await page.reload();
  await page.getByLabel("Webhook URL").fill(`http://127.0.0.1:${port}/hook`);
  await page.getByTestId("create-webhook").click();
  const secret = (await page.getByTestId("secret-value").textContent())!.trim();
  await page.getByTestId("test-webhook").click();
  await expect(page.getByText("Delivered (HTTP 200)")).toBeVisible();
  await expect(page.getByTestId("deliveries")).toContainText("ping");
  expect(received.length).toBe(1);
  const sig = "sha256=" + createHmac("sha256", secret).update(received[0].body).digest("hex");
  expect(received[0].headers["x-studio-signature"]).toBe(sig);
  server.close();
});

test("free users see the API as a Business feature", async ({ page }) => {
  const a = await createMember("member");
  await login(page, a.email);
  await page.goto("/account/developer");
  await expect(page.getByText("The API and webhooks are part of Business.")).toBeVisible();
  await expect(page.getByTestId("locked-api_access")).toBeVisible();
});
