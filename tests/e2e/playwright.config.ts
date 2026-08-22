// P122 Phase 3: Playwright E2E 配置
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./",
  testMatch: "**/*.spec.ts",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    headless: true,
    channel: "chromium",
  },
  workers: 1,
  retries: 1,
  reporter: [["line"]],
  forbidOnly: true,
});
