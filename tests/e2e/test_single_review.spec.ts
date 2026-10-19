import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import * as path from "path";
import { fileURLToPath } from "url";

const FIXTURE_DIR =
  process.env.E2E_FIXTURE_DIR ||
  path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

// 上传 DXF 到图纸管理页并触发解析（关闭 YOLO 走纯规则链路）
async function uploadDrawing(page: Page, file: string): Promise<void> {
  await page.goto("/");
  await page.click('[data-page="drawings"]');
  const yolo = page.locator("#use-yolo-checkbox");
  if (await yolo.isChecked()) await yolo.uncheck();
  await page.setInputFiles("#file-input", `${FIXTURE_DIR}/${file}`);
  await page.click('[data-action="uploadAndReview"]');
  // 等待解析完成（列表计数 > 0），确保审查下拉已刷新，避免打开面板时仍是占位项
  await expect(page.locator("#drawing-count")).toHaveText(/[1-9]/, { timeout: 120_000 });
}

test.describe("单图审查流程", () => {
  test("上传 DXF → 提交审查 → 查看结果", async ({ page }) => {
    test.slow();
    await uploadDrawing(page, "test_basic.dxf");

    // 打开审查面板
    await page.click('[data-action="showDrawingReviewPanel"]');

    const sel = page.locator("#review-drawing-select");
    await expect(sel).toBeVisible({ timeout: 15_000 });
    // 0 为占位项 "— 选择已解析图纸 —"，1 为刚上传的图纸
    await sel.selectOption({ index: 1 });

    const startBtn = page.locator("#review-start-btn");
    await expect(startBtn).toBeEnabled({ timeout: 15_000 });
    await startBtn.click();

    // 审查结果写入 window._currentReviewResult，status=success 表示审查链路成功
    await page.waitForFunction(
      () => (window as any)._currentReviewResult?.status === "success",
      undefined,
      { timeout: 180_000 },
    );
    await expect(page.locator("#review-summary")).toHaveText(/\S/);
  });
});
