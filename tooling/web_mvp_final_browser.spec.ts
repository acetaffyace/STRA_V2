import { test, expect } from "@playwright/test";

test("STEINS;GATE RE:BOOT final Web MVP smoke", async ({ page }) => {
  await page.goto("http://127.0.0.1:3000/dashboard?game=4012810");
  await expect(page.getByText("500", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("live_provider", { exact: false })).toBeVisible();
  await expect(page.getByText("deepseek-v4-flash", { exact: false })).toBeVisible();
  await expect(page.getByText("82.6%", { exact: false })).toBeVisible();
  await expect(page.getByText("Current Snapshot", { exact: false })).toBeVisible();
  await expect(page.getByText("Unavailable", { exact: false })).not.toHaveCount(0);
});
