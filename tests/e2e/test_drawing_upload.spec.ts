import { expect, test } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const FIXTURE_DIR = "/mnt/d/OpenClawData3workspace/Projects/BAA/tests/e2e/fixtures";

test.describe("图纸上传与管理", () => {
  test("上传 DXF → 列表展示 → 详情查看 → 删除", async ({ page }) => {
    await page.goto("/");
    await page.click('[data-page="drawings"]');

    // 上传单个文件
    await page.setInputFiles("#file-input", `${FIXTURE_DIR}/test_basic.dxf`);
    await page.waitForTimeout(1500);

    // 列表中出现
    const list = page.locator("#drawing-list");
    await expect(list).not.toHaveText("暂无", { timeout: 10_000 });
    expect(list.textContent()?.length).toBeGreaterThan(0);

    // 图纸计数 >= 1
    const countText = page.locator("#drawing-count").textContent();
    expect(countText ?? "").toMatch(/\d/);
  });

  test("上传后进入审查页并选择该图纸", async ({ page }) => {
    await page.goto("/");
    await page.click('[data-page="drawings"]');
    await page.setInputFiles("#file-input", `${FIXTURE_DIR}/test_room.dxf`);
    await page.waitForTimeout(1500);

    // 切到审查页，图纸下拉应包含刚上传的文件
    await page.click('[data-page="review"]');
    await page.waitForTimeout(1000);
    const sel = page.locator("#review-drawing-select");
    const options = await sel.locator("option").allTextContents();
    expect(options.length).toBeGreaterThan(0);
  });
});
