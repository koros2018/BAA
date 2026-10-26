"""D1-T4 集成测试：同图双跑验证 scale_overrides 生效。

核心断言：
1. review-from-data 接受 standard_set_code body 参数并正确回传 standard_set_code/name/version
2. 同一份 entities 数据分别跑 CN-National-v1 vs CN-Shanghai-v1 → violation_by_clause 有差异
3. Shanghai 地标覆盖的 clause_id 出现在 violation_by_clause 里（或差异可观测）

关键实体格式：
- entity.type 必须匹配原子函数的 target_entities
- entity.properties 是 _extract_value 读取的字段（不是 attributes）
- DIM-001/003/004/113 用 width 字段提取宽度值
- DIST-001 用 travel_distance 提取疏散距离值

测试顺序：先 National 再 Shanghai（避免全局 AtomicFunction.threshold 被污染）
"""

from __future__ import annotations

import pytest

# ── Shanghai 地标可观测 diff 的 entities ──
#
# DIM-001 (GB50016-5.5.18): 疏散楼梯净宽判定
#   target=['staircase', 'stair']
#   National threshold: 1.2m (SpecRepository)
#   Shanghai threshold: 1.3m (scale_override)
#   用 stair width=1.25m → 国标 1.25>=1.2 PASS / 上海 1.25<1.3 FAIL ✅
#
# DIM-003 (GB50016-7.1.1): 消防车道宽度判定
#   target=['fire_lane', 'road', 'driveway']
#   National threshold: 4.0m (SpecRepository)
#   Shanghai threshold: 4.5m (scale_override)
#   用 road width=4.2m → 国标 4.2>=4.0 PASS / 上海 4.2<4.5 FAIL ✅
ENTITIES_SHANGHAI_DIFF = [
    {
        "id": "s-diff-1",
        "type": "stair",
        "properties": {
            "width": 1.25,
        },
    },
    {
        "id": "r-diff-1",
        "type": "road",
        "properties": {
            "width": 4.2,
        },
    },
]

# ── Guangdong 地标可观测 diff 的 entities ──
#
# DIST-001 (GB50016-5.5.17): 房间疏散距离判定
#   提取 travel_distance（不是 exit_distance！）
#   National threshold: 30.0m (SpecRepository, operator<=)
#   Guangdong threshold: 25.0m (scale_override, operator<=)
#   用 room travel_distance=27m → 国标 27<=30 PASS / 广东 27>25 FAIL ✅
ENTITIES_GUANGDONG_DIFF = [
    {
        "id": "room-diff-1",
        "type": "room",
        "properties": {
            "travel_distance": 27.0,
        },
    },
]


class TestReviewFromDataStandardSet:
    """D1-T4/D1-T6：review-from-data 标准集切换集成验证。"""

    # ── 测试 1：正确回传 standard_set_code/name/version ──

    def test_review_returns_requested_standard_set_metadata(self, client):
        """POST standard_set_code 后 response_data 应回传 code/name/version。"""
        resp = client.post(
            "/review-from-data",
            json={
                "entities": ENTITIES_SHANGHAI_DIFF,
                "building_type": "civil",
                "standard_set_code": "CN-National-v1",
            },
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp.status_code == 200, f"status={resp.status_code}: {resp.text[:200]}"
        data = resp.json()

        assert data["status"] == "success"
        assert data["standard_set_code"] == "CN-National-v1"
        assert data["standard_set_name"] == "中国国家级标准（v1）"
        assert data["standard_set_version"] == "v1"

    def test_review_shanghai_metadata(self, client):
        """上海地标集也应正确回传元数据。"""
        resp = client.post(
            "/review-from-data",
            json={
                "entities": ENTITIES_SHANGHAI_DIFF,
                "building_type": "civil",
                "standard_set_code": "CN-Shanghai-v1",
            },
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp.status_code == 200, f"status={resp.status_code}: {resp.text[:200]}"
        data = resp.json()

        assert data["status"] == "success"
        assert data["standard_set_code"] == "CN-Shanghai-v1"
        assert data["standard_set_name"] == "中国 上海地方标准（v1）"
        assert data["standard_set_version"] == "v1"

    # ── 测试 2：未知 code 返回错误 ──

    def test_unknown_standard_set_code_returns_error(self, client):
        """未知 standard_set_code 应返回 UNKNOWN_STANDARD_SET 错误。"""
        resp = client.post(
            "/review-from-data",
            json={
                "entities": ENTITIES_SHANGHAI_DIFF,
                "building_type": "civil",
                "standard_set_code": "NONEXISTENT-v9",
            },
            headers={"Authorization": "Bearer test-api-key"},
        )
        data = resp.json()
        assert resp.status_code == 200
        assert data["status"] == "error"
        assert data.get("error_code") == "UNKNOWN_STANDARD_SET"

    # ── 测试 3：同图双跑 diff（上海地标） ──

    def test_same_entities_different_standard_sets_produce_different_results(self, client):
        """同一份 entities → CN-National vs CN-Shanghai → violation_by_clause 应不同。

        DIM-001 (GB50016-5.5.18): stair width 1.25m
          National threshold=1.2m → 1.25 >= 1.2 → PASS
          Shanghai  threshold=1.3m → 1.25 < 1.3 → FAIL
        DIM-003 (GB50016-7.1.1): road width 4.2m
          National threshold=4.0m → 4.2 >= 4.0 → PASS
          Shanghai  threshold=4.5m → 4.2 < 4.5 → FAIL

        断言：至少一个 clause 在 Shanghai 下 violation 次数 > National。

        注意：测试顺序 National→Shanghai，避免全局 AtomicFunction.threshold 被污染。
        """
        # Step 1: CN-National-v1
        resp_nat = client.post(
            "/review-from-data",
            json={
                "entities": ENTITIES_SHANGHAI_DIFF,
                "building_type": "civil",
                "standard_set_code": "CN-National-v1",
            },
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp_nat.status_code == 200, resp_nat.text[:200]
        j_nat = resp_nat.json()
        assert j_nat["standard_set_code"] == "CN-National-v1"

        # Step 2: CN-Shanghai-v1（同图）
        resp_sh = client.post(
            "/review-from-data",
            json={
                "entities": ENTITIES_SHANGHAI_DIFF,
                "building_type": "civil",
                "standard_set_code": "CN-Shanghai-v1",
            },
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp_sh.status_code == 200, resp_sh.text[:200]
        j_sh = resp_sh.json()
        assert j_sh["standard_set_code"] == "CN-Shanghai-v1"

        # Step 3: diff 断言
        v_nat = j_nat.get("summary", {}).get("violation_by_clause", {}) or {}
        v_sh = j_sh.get("summary", {}).get("violation_by_clause", {}) or {}

        # 上海地标覆盖的 clause_ids（已在 _extract_value 列表里，可被 execute 到）
        landmark_clauses = {
            "GB50016-5.5.18",    # DIM-001, DIM-004 (上海 civil=1.3)
            "GB50016-7.1.1",     # DIM-003 (上海 civil=4.5)
        }

        # 严格断言：Shanghai 下至少一个地标覆盖 clause 的 violation 次数 > National
        diff_clauses = {
            k: v for k, v in v_sh.items() if k not in v_nat or v > v_nat.get(k, 0)
        }
        landmark_diff = {
            k: v for k, v in diff_clauses.items() if k in landmark_clauses
        }
        assert (
            len(landmark_diff) > 0
        ), (
            f"地标覆盖的 clause 未在 diff 中出现！\n"
            f"National violations: {j_nat.get('summary', {}).get('violations')}\n"
            f"Shanghai violations: {j_sh.get('summary', {}).get('violations')}\n"
            f"Nat violation_by_clause: {v_nat}\n"
            f"Sh violation_by_clause: {v_sh}"
        )

    # ── 测试 4：广东地标也生效 ──

    def test_guangdong_landmark_also_produces_diff_vs_national(self, client):
        """CN-Guangdong-v1 应与 CN-National-v1 有 diff（DIST-001 疏散距离 27m vs 25m）。"""
        resp_nat = client.post(
            "/review-from-data",
            json={
                "entities": ENTITIES_GUANGDONG_DIFF,
                "building_type": "civil",
                "standard_set_code": "CN-National-v1",
            },
            headers={"Authorization": "Bearer test-api-key"},
        )
        resp_gd = client.post(
            "/review-from-data",
            json={
                "entities": ENTITIES_GUANGDONG_DIFF,
                "building_type": "civil",
                "standard_set_code": "CN-Guangdong-v1",
            },
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp_nat.status_code == 200
        assert resp_gd.status_code == 200
        j_nat = resp_nat.json()
        j_gd = resp_gd.json()

        v_nat = j_nat.get("summary", {}).get("violation_by_clause", {}) or {}
        v_gd = j_gd.get("summary", {}).get("violation_by_clause", {}) or {}

        gd_landmark_clauses = {
            "GB50016-5.5.17",    # DIST-001 (广东 civil=25.0, operator<=)
        }
        diff_clauses = {
            k: v for k, v in v_gd.items() if k not in v_nat or v > v_nat.get(k, 0)
        }
        landmark_diff = {
            k: v for k, v in diff_clauses.items() if k in gd_landmark_clauses
        }
        assert (
            len(landmark_diff) > 0
        ), (
            f"广东地标 clause 未在 diff 中出现！\n"
            f"Nat violations: {j_nat.get('summary', {}).get('violations')}\n"
            f"GD violations: {j_gd.get('summary', {}).get('violations')}\n"
            f"Nat violation_by_clause: {v_nat}\n"
            f"GD violation_by_clause: {v_gd}"
        )

    # ── 测试 5：缺省 standard_set_code 为 CN-National-v1 ──

    def test_missing_standard_set_code_defaults_to_national(self, client):
        """不传 standard_set_code → 应缺省 CN-National-v1。"""
        resp = client.post(
            "/review-from-data",
            json={
                "entities": ENTITIES_SHANGHAI_DIFF,
                "building_type": "civil",
            },
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["standard_set_code"] == "CN-National-v1"


# ── GET /api/v1/standards 端点 ──


class TestStandardsEndpoint:
    """GET /api/v1/standards 返回 4 个内置标准集元数据。"""

    def test_standards_endpoint_returns_four_sets(self, client):
        resp = client.get("/api/v1/standards")
        assert resp.status_code == 200
        data = resp.json()

        assert data["count"] == 4
        codes = {s["code"] for s in data["sets"]}
        assert codes == {
            "CN-National-v1",
            "CN-Shanghai-v1",
            "CN-Guangdong-v1",
            "US-NFPA-v1",
        }

    def test_standards_endpoint_scale_overrides_counts(self, client):
        """上海和广东地标集 scale_overrides_count 应 > 0。"""
        resp = client.get("/api/v1/standards")
        data = resp.json()

        by_code = {s["code"]: s for s in data["sets"]}
        assert by_code["CN-Shanghai-v1"]["scale_overrides_count"] == 3
        assert by_code["CN-Guangdong-v1"]["scale_overrides_count"] == 3
        assert by_code["CN-National-v1"]["scale_overrides_count"] == 0
        assert by_code["US-NFPA-v1"]["scale_overrides_count"] == 0

    def test_standards_endpoint_included_standards(self, client):
        """国标集 included_standards 数应为 5；NFPA 集应为 4。"""
        resp = client.get("/api/v1/standards")
        data = resp.json()
        by_code = {s["code"]: s for s in data["sets"]}

        assert len(by_code["CN-National-v1"]["included_standards"]) == 5
        assert len(by_code["CN-Shanghai-v1"]["included_standards"]) == 5
        assert len(by_code["CN-Guangdong-v1"]["included_standards"]) == 5
        assert len(by_code["US-NFPA-v1"]["included_standards"]) == 4
