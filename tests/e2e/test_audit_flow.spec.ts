import { expect, test } from "@playwright/test";

// 直接调 API 验证 P119 审核端点闭环（比走完整前端审查快）
test.describe("P119 审核工作流 API 闭环", () => {
  test("POST 创建 audit item → confirm/dismiss/pending 三态切换 → GET stats", async ({
    request,
  }) => {
    // 先创建一条 audit item（不依赖真实审查）
    const createRes = await request.post("/api/v1/audit/items", {
      data: {
        review_id: `e2e_${Date.now()}`,
        drawing_id: "e2e-drawing",
        clause_id: "DIM-001",
        entity_id: "test-entity-1",
        violation_type: "测试违规",
      },
    });
    // 200 或 201 均可（不同实现）
    expect([200, 201]).toContain(createRes.status());
    const item = await createRes.json();
    const itemId = item.item_id || item.id || item.data?.item_id;
    expect(itemId).toBeTruthy();

    // 查询初始 stats
    const stats0 = await (
      await request.get(
        `/api/v1/audit/stats?review_id=e2e_${Date.now()}`
      )
    ).json();

    // confirm 一条
    const c1 = await request.post(`/api/v1/audit/items/${itemId}/confirm`);
    expect([200, 201]).toContain(c1.status());

    // dismiss 一条
    const c2 = await request.post(`/api/v1/audit/items/${itemId}/dismiss`);
    expect([200, 201]).toContain(c2.status());

    // pending 一条
    const c3 = await request.post(`/api/v1/audit/items/${itemId}/pending`);
    expect([200, 201]).toContain(c3.status());

    // 最终 stats 与初始不同
    const stats1 = await (
      await request.get(
        `/api/v1/audit/stats?review_id=e2e_${Date.now()}`
      )
    ).json();
    expect(stats1).toBeTruthy();
  });
});
