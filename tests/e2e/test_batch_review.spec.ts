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

    // 点击批量送审按钮（start-btn）
    const batchBtn = page.locator("#batch-review-start-btn");
    await expect(batchBtn).toBeVisible({ timeout: 10_000 });
    await batchBtn.click();

    // 等待批量结果出现：summary 或 details 有内容（二选一即可）
    await Promise.race([
      page
        .locator("#batch-review-summary")
        .waitFor({ state: "visible", timeout: 180_000 }),
      page
        .locator("#batch-review-details")
        .waitFor({ state: "visible", timeout: 180_000 }),
    ]);

    // 至少 summary 或 details 非空
    const summaryText = (await page.locator("#batch-review-summary").textContent())?.trim() || "";
    const detailsCount = await page.locator("#batch-review-details > div").count();
    expect(summaryText.length > 0 || detailsCount > 0).toBe(true);
  });
});
