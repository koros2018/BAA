import { test } from "@playwright/test";

test("smoke", async ({ page }) => {
  await page.goto("http://127.0.0.1:8000/");
  console.log("[SMOKE] loaded");
});
