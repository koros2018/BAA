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
});
