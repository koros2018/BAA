import { expect, test } from "@playwright/test";

// 直接调 API 验证 P119 审核端点闭环（比走完整前端审查快）
test.describe("P119 审核工作流 API 闭环", () => {
  test("批量创建 audit items → confirm/dismiss/pending 三态切换 → GET stats", async ({
    request,
  }) => {
    const reviewId = `e2e_${Date.now()}`;

    // 先创建多条 audit item（POST 接受 details 数组）
    const createRes = await request.post("/api/v1/audit/items", {
      data: {
        review_id: reviewId,
        details: [
          { clause_id: "DIM-001", entity_id: "ent-1", violation_type: "宽度过窄" },
          { clause_id: "EXIST-001", entity_id: "ent-2", violation_type: "消防设施缺失" },
          { clause_id: "DIM-002", entity_id: "ent-3", violation_type: "尺寸不合规" },
        ],
      },
    });
    expect([200, 201]).toContain(createRes.status());
    const created = await createRes.json();
    expect((created.created as number) ?? 0).toBeGreaterThanOrEqual(1);

    // 拉取已创建条目，拿到 item_id
    const listRes = await request.get(
      `/api/v1/audit/items?review_id=${encodeURIComponent(reviewId)}`
    );
    expect(listRes.status()).toBe(200);
    const listData = await listRes.json();
    const items = listData.items || [];
    expect(items.length).toBeGreaterThanOrEqual(1);
    const itemId = items[0].item_id || items[0].id;
    expect(itemId).toBeTruthy();

    // confirm / dismiss / pending 三态切换
    const c1 = await request.post(`/api/v1/audit/items/${itemId}/confirm`);
    expect([200, 201]).toContain(c1.status());

    const c2 = await request.post(`/api/v1/audit/items/${itemId}/dismiss`, {
      data: { reason: "e2e 测试驳回" },
    });
    expect([200, 201]).toContain(c2.status());

    const c3 = await request.post(`/api/v1/audit/items/${itemId}/pending`);
    expect([200, 201]).toContain(c3.status());

    // stats 端点可达（query 参数）
    const statsRes = await request.get(
      `/api/v1/audit/stats?review_id=${encodeURIComponent(reviewId)}`
    );
    expect(statsRes.status()).toBeLessThan(500);
    const stats = await statsRes.json();
    expect(stats).toBeTruthy();
  });
});
