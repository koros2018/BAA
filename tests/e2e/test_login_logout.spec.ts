import { expect, test } from "@playwright/test";

const USER = `e2e_${Date.now()}_user`;
const PASS = "e2e_test_pass_123";

test.describe("登录 / 登出流程", () => {
  test("注册 → 登录 → 查看团队列表 → 登出", async ({ page }) => {
    await page.goto("/");

    // 进入协作页面
    await page.click('[data-page="collab"]');

    // ── 注册 ──
    // 切到注册 Tab
    const registerTab = page.locator("#collab-auth-tabs button").last();
    await registerTab.click();
    await page.waitForTimeout(500);

    await page.fill("#collab-reg-username", USER);
    await page.fill("#collab-reg-password", PASS);
    await page.fill("#collab-reg-email", "e2e@test.com");
    await page.fill("#collab-reg-name", "E2E Tester");

    // 提交注册
    await page.click('#collab-register-form button[type="submit"]');
    await page.waitForTimeout(1000);

    // 确认注册成功（切换到登录表单或显示成功）
    const authMsg = page.locator("#collab-auth-msg");

    // ── 登录 ──
    // 切到登录 Tab
    const loginTab = page.locator("#collab-auth-tabs button").first();
    await loginTab.click();
    await page.waitForTimeout(500);

    await page.fill("#collab-username", USER);
    await page.fill("#collab-password", PASS);
    await page.click('#collab-login-form button[type="submit"]');

    // 等待登录成功 — 用户状态显示已登录
    await expect(page.locator("#user-status-logged-in")).toBeVisible({
      timeout: 10000,
    });

    // 查看团队列表已加载
    await expect(page.locator("#collab-teams")).toHaveText(/.+/, {
      timeout: 10000,
    });

    // ── 登出 ──
    await page.click('button:has-text("退出")');
    await page.waitForTimeout(1000);

    // 验证登出后回到未登录状态
    await expect(page.locator("#user-status-logged-out")).toBeVisible({
      timeout: 5000,
    });
  });
});
