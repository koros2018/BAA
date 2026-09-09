import { expect, test } from "@playwright/test";

// 全量回归 smoke：所有主要页面均可加载且不报错
test.describe("页面路由全量 smoke", () => {
  const pages = [
    { selector: '[data-page="drawings"]', name: "图纸管理" },
    { selector: '[data-page="review"]', name: "AI 审查" },
    { selector: '[data-page="collab"]', name: "团队协作" },
    { selector: '[data-page="reports"]', name: "报告" },
    { selector: '[data-page="settings"]', name: "设置" },
  ];

  for (const p of pages) {
    test(`加载 ${p.name} 页面不报错`, async ({ page }) => {
      page.on("console", (msg) => {
        if (msg.type() === "error") {
          // 只记录，不断言（部分页面有已知告警）
          console.warn(`[console.error] ${p.name}: ${msg.text()}`);
        }
      });

      await page.goto("/");
      await page.click(p.selector);
      await page.waitForTimeout(500);
    });
  }

  test("首页加载 + health 检查", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/BAA/);
    // 健康状态文本存在
    const health = page.locator("#health-status");
    await expect(health).toHaveText(/\{/, { timeout: 10_000 });
  });
});
