import { expect, test } from "@playwright/test";
import { createMember, login } from "./helpers";

test("new caption styles and split-screen framing are available in the maker", async ({ page }) => {
  const a = await createMember("member");
  await login(page, a.email);
  await page.goto("/clipper/new");
  for (const id of ["neon", "typewriter", "bounce"]) {
    await page.getByTestId(`preset-${id}`).click();
    await expect(page.getByTestId("caption-preview")).toBeVisible();
  }
  await page.getByTestId("reframe-split").click();
  await expect(page.getByTestId("reframe-split")).toHaveAttribute("aria-pressed", "true");
});
