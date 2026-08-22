import { expect, test } from "@playwright/test";

const FIXTURE_DIR = "/mnt/d/OpenClawData3workspace/Projects/BAA/tests/e2e/fixtures";

test.describe("批量审查流程", () => {
  test("上传多个 DXF → 批量送审 → 查看结果", async ({ page }) => {
    await page.goto("/");

    // 进入图纸管理页面
    await page.click('[data-page="drawings"]');

    // 多文件上传
    await page.setInputFiles("#batch-file-input", [
      `${FIXTURE_DIR}/test_basic.dxf`,
      `${FIXTURE_DIR}/test_batch.dxf`,
      `${FIXTURE_DIR}/test_room.dxf`,
    ]);

    // 等待文件加载到队列
    await page.waitForTimeout(2000);

    // 点击批量送审按钮
    const batchBtn = page.locator("#batch-review-btn");
    await expect(batchBtn).toBeVisible({ timeout: 5000 });
    await batchBtn.click();

    // 等待批量结果出现
    await expect(
      page.locator("#batch-results").locator("div").first()
    ).toHaveText(/.+/, { timeout: 120000 });
  });
});
