import { expect, test } from "@playwright/test";
import * as path from "path";
import { fileURLToPath } from "url";

const FIXTURE_DIR =
  process.env.E2E_FIXTURE_DIR ||
  path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

test.describe("批量审查流程", () => {
  test("上传多张 DXF → 勾选送审 → 查看批量结果", async ({ page }) => {
    test.slow();
    await page.goto("/");
    await page.click('[data-page="drawings"]');
    const yolo = page.locator("#use-yolo-checkbox");
    if (await yolo.isChecked()) await yolo.uncheck();

    // 逐张上传解析（列表逐张累积）
    const files = ["test_basic.dxf", "test_batch.dxf", "test_room.dxf"];
    for (let i = 0; i < files.length; i++) {
      await page.setInputFiles("#file-input", `${FIXTURE_DIR}/${files[i]}`);
      await page.click('[data-action="uploadAndReview"]');
      await expect(page.locator("#drawing-count")).toHaveText(String(i + 1), { timeout: 120_000 });
    }

    // 全选 → 批量送审：走图纸列表多选 → batchReview() → /review-from-data
    await page.click('[data-action="selectAllDrawings"]');
    const batchBtn = page.locator("#batch-review-btn");
    await expect(batchBtn).toBeVisible({ timeout: 10_000 });
    await batchBtn.click();

    await expect(page.locator("#upload-progress")).toContainText("批量审查完成", { timeout: 120_000 });
    await expect(page.locator("#upload-progress")).toContainText("项违规", { timeout: 10_000 });
  });

  test("TD-E2E-005 守护：SSE 批量审查 Tab 选择文件后点击触发 /batch-review-stream", async ({ page }) => {
    await page.goto("/");
    await page.click('[data-page="drawings"]');
    // 审查面板默认 hidden，批量 Tab 不依赖已载图纸，直接展开
    await page.evaluate(
      () => (window as unknown as { showDrawingReviewPanel?: (v: boolean) => void }).showDrawingReviewPanel?.(true),
    );
    await page.click("#dr-tab-batch");
    await expect(page.locator("#dr-panel-batch")).toBeVisible();

    await page.setInputFiles("#batch-file-input", `${FIXTURE_DIR}/test_basic.dxf`);
    // 根因①守护：change 事件必须写入 window.batchFiles（修复前全仓无赋值点）
    const n = await page.evaluate(
      () => (window as unknown as { batchFiles?: FileList }).batchFiles?.length ?? 0,
    );
    expect(n).toBe(1);

    // 根因②守护：点击开始必须真正发起 SSE 请求（修复前 data-action 名不匹配静默 no-op）
    const reqPromise = page.waitForRequest(
      (r) => r.url().includes("/batch-review-stream") && r.method() === "POST",
      { timeout: 15_000 },
    );
    await page.click("#batch-review-start-btn");
    await reqPromise;
  });
});
