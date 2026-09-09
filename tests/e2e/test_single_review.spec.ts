import { expect, test } from "@playwright/test";

const FIXTURE_DIR = "/mnt/d/OpenClawData3workspace/Projects/BAA/tests/e2e/fixtures";

test.describe("单图审查流程", () => {
  test("上传 DXF → 提交审查 → 查看结果", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/BAA/);

    // 进入图纸管理页面
    await page.click('[data-page="drawings"]');

    // 上传 DXF 文件
    await page.setInputFiles("#file-input", `${FIXTURE_DIR}/test_basic.dxf`);

    // 等待上传完成（图纸出现在列表中）
    await page.waitForTimeout(2000);

    // 切换到 AI 审图页面
    await page.click('[data-page="review"]');
    await page.waitForTimeout(1000);

    // 点击开始审查
    await page.click("#review-start-btn");

    // 等待审查完成：summary 或 details 可见，或 loading 消失
    await Promise.race([
      page
        .locator("#review-summary")
        .waitFor({ state: "visible", timeout: 180_000 }),
      page
        .locator("#review-details")
        .waitFor({ state: "visible", timeout: 180_000 }),
    ]);

    // 审查后 loading 消失，summary/details 中至少一个有内容
    const summary = (await page.locator("#review-summary").textContent())?.trim() || "";
    const detailsCount = await page.locator("#review-details > div").count();
    expect(summary.length > 0 || detailsCount > 0).toBe(true);
  });
});
