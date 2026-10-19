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

test.describe("图纸上传与管理", () => {
  test("上传 DXF → 列表展示 → 详情查看 → 删除", async ({ page }) => {
    test.slow();
    await uploadDrawing(page, "test_basic.dxf");

    // 列表展示：#drawing-list 为 tbody，行渲染为 tr
    const rows = page.locator("#drawing-list tr");
    await expect(rows.first()).toBeVisible({ timeout: 120_000 });
    expect(await rows.count()).toBeGreaterThan(0);
    await expect(page.locator("#drawing-count")).toHaveText(/[1-9]/);

    // 详情查看：解析结果 JSON 已填充
    await expect(page.locator("#parse-result-json")).toHaveText(/\S/, { timeout: 30_000 });

    // 删除：接受 confirm 弹窗，列表回归空态
    page.once("dialog", (d) => d.accept());
    await page.click('#drawing-list button[onclick^="deleteDrawing"]');
    await expect(page.locator("#drawing-count")).toHaveText("0", { timeout: 15_000 });
    await expect(page.locator("#drawing-list")).toContainText("暂无记录");
  });

  test("上传后进入审查页并选择该图纸", async ({ page }) => {
    test.slow();
    await uploadDrawing(page, "test_room.dxf");

    // 审查面板（原 AI 审图 Tab 已内嵌至图纸管理页）
    await page.click('[data-action="showDrawingReviewPanel"]');
    const sel = page.locator("#review-drawing-select");
    await expect(sel).toBeVisible({ timeout: 15_000 });

    // 占位项 + 已解析图纸 => options 数 > 1
    const options = await sel.locator("option").allTextContents();
    expect(options.length).toBeGreaterThan(1);
  });
});
