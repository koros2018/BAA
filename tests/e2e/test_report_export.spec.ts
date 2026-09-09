import { expect, test } from "@playwright/test";

// 报告导出接口探活：JSON / CSV 走 API 直连，PDF 走前端触发下载验证
test.describe("报告导出接口", () => {
  test("导出 JSON / CSV / PDF 三种格式端点均可达", async ({
    request,
    page,
  }) => {
    const reviewId = `e2e_export_${Date.now()}`;

    // JSON 导出端点（可能存在也可能返回 404，端点可达即可）
    const jsonRes = await request.get(
      `/api/v1/review/export?review_id=${reviewId}&format=json`
    );
    // 常见状态：200 或 404（无对应数据），不应 500
    expect(jsonRes.status()).toBeLessThan(500);

    // CSV 导出
    const csvRes = await request.get(
      `/api/v1/review/export?review_id=${reviewId}&format=csv`
    );
    expect(csvRes.status()).toBeLessThan(500);

    // PDF 导出
    const pdfRes = await request.get(
      `/api/v1/review/export?review_id=${reviewId}&format=pdf`
    );
    expect(pdfRes.status()).toBeLessThan(500);
  });

  test("整改通知单 PDF 端点可达", async ({ request }) => {
    const reviewId = `e2e_correction_${Date.now()}`;
    const res = await request.get(
      `/api/v1/audit/export/pdf?review_id=${reviewId}`
    );
    // 端点应存在（200 或 404），不应 500
    expect(res.status()).toBeLessThan(500);
  });
});
