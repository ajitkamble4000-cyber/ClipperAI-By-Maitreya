import { expect, test, type Page } from "@playwright/test";
import { createMember, ensureOwner, login, rest } from "./helpers";

const KEY_ID = "rzp_test_E2Ekey123456";
const SECRET = "e2e_key_secret_value";

/**
 * Stand-in for Razorpay Checkout (checkout.razorpay.com is not reachable in tests): "pays" immediately and signs
 * the result the way Razorpay does, HMAC-SHA256(order_id|payment_id, key secret), so the server's check is real.
 */
async function fakeRazorpay(page: Page) {
  await page.route("https://checkout.razorpay.com/**", (route) =>
    route.fulfill({
      contentType: "text/javascript",
      body: `window.Razorpay = function (opts) {
        this.on = function () {};
        this.open = async function () {
          const pid = "pay_e2e" + Math.random().toString(36).slice(2, 10);
          const enc = new TextEncoder();
          const key = await crypto.subtle.importKey("raw", enc.encode(${JSON.stringify(SECRET)}), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
          const sig = await crypto.subtle.sign("HMAC", key, enc.encode(opts.order_id + "|" + pid));
          const hex = Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, "0")).join("");
          window.__rzp = { amount: opts.amount, currency: opts.currency, name: opts.name, email: opts.prefill && opts.prefill.email };
          opts.handler({ razorpay_order_id: opts.order_id, razorpay_payment_id: pid, razorpay_signature: hex });
        };
      };`,
    }),
  );
}

test("owner connects Razorpay; a member buys Pro and a token pack; admin sees the revenue", async ({ page, browser }) => {
  const owner = await ensureOwner();
  try {
    // owner pastes the keys
    await login(page, owner.email);
    await page.goto("/admin/payments");
    await expect(page.getByTestId("razorpay-status")).toHaveText("Not connected");
    await expect(page.getByTestId("webhook-url")).toHaveText(/\/billing\/razorpay\/webhook$/);
    await page.getByLabel("Key ID").fill(KEY_ID);
    await page.getByLabel("Key secret").fill(SECRET);
    await page.getByLabel("Webhook secret").fill("e2e_webhook_secret");
    await page.getByTestId("save-razorpay").click();
    await expect(page.getByText("Razorpay is connected. Payments are on.")).toBeVisible();
    await expect(page.getByTestId("razorpay-status")).toHaveText("Test mode");
    await page.getByRole("button", { name: "Test keys" }).click();
    await expect(page.getByText("Keys work (test mode)")).toBeVisible();

    // a member pays for Pro
    const m = await createMember("member");
    const ctx = await browser.newContext();
    const mp = await ctx.newPage();
    await fakeRazorpay(mp);
    await login(mp, m.email);
    await mp.goto("/pricing");
    await expect(mp.getByTestId("price-pro")).toContainText("₹1,499");
    await mp.getByRole("button", { name: /Yearly/ }).click();
    await expect(mp.getByTestId("price-pro")).toContainText("₹14,990");
    await mp.getByRole("button", { name: "Monthly" }).click();
    await mp.getByTestId("buy-pro").click();
    await expect(mp.getByText(/You're on Pro until/)).toBeVisible();
    expect(await mp.evaluate(() => (window as unknown as { __rzp: { amount: number; currency: string; email: string } }).__rzp)).toMatchObject({
      amount: 149900,
      currency: "INR",
      email: m.email,
    });
    await expect(mp.getByTestId("plan-pro").getByTestId("current-plan")).toBeVisible();
    await expect(mp.getByTestId("buy-pro")).toHaveText("Renew for ₹1,499");

    await mp.goto("/account");
    await expect(mp.getByTestId("account-plan")).toHaveText("Pro");
    await expect(mp.getByTestId("paid-until")).toContainText("Pro paid until");
    await expect(mp.getByTestId("payments")).toContainText("Pro plan, 1 month");
    await expect(mp.getByTestId("payments")).toContainText("₹1,499");

    // and a token pack
    await mp.goto("/account/tokens");
    await expect(mp.getByTestId("tokens-total")).toHaveText("5,000"); // Pro allowance applied today
    await mp.getByTestId("buy-pack-starter").click();
    await expect(mp.getByText("5,000 tokens added. Thank you!")).toBeVisible();
    await expect(mp.getByTestId("tokens-total")).toHaveText("10,000");
    await expect(mp.getByTestId("ledger")).toContainText("Bought");
    await ctx.close();

    // the owner sees both payments
    await page.goto("/admin/payments");
    await page.getByLabel("Search payments").fill(m.email);
    await expect(page.getByTestId("payments-table").locator("tbody tr")).toHaveCount(2);
    await expect(page.getByTestId("payments-table")).toContainText("Starter pack: 5,000 tokens");
    await expect(page.getByTestId("revenue-30d")).not.toHaveText("₹0");
  } finally {
    // other specs expect payments to be off (upgrade requests instead)
    await rest("settings?id=eq.1", "PATCH", { razorpay_key_id: null, razorpay_secret_enc: null, razorpay_webhook_secret_enc: null });
  }
});
