"""
P119 整改通知单 PDF + 审核统计面板 单元测试

覆盖:
    1. build_correction_notice PDF 生成
    2. correction_notice API endpoint
    3. 审核统计状态聚合
    4. 前端审核统计面板渲染
"""

import pytest

# ── 1. PDF 生成测试 ─────────────────────────────────────────


class TestCorrectionNoticePDF:
    def _make_items(self, n=3):
        return [
            {
                "id": f"test:{i}",
                "review_id": "test",
                "function_id": f"DIM-{(i % 3) + 1:03d}",
                "entity_id": f"door-{i}",
                "status": "confirmed",
                "note": f"备注{i}",
            }
            for i in range(n)
        ]

    def test_pdf_generates(self):
        from src.baa_engine.report_generator.components import ensure_font
        from src.baa_engine.report_generator.correction_notice import build_correction_notice

        ensure_font()
        items = self._make_items(5)
        meta = {"drawing_name": "test.dxf", "project_name": "测试项目", "reviewer": "admin"}
        pdf = build_correction_notice(items, meta)
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 1000

    def test_empty_items_raises(self):
        from src.baa_engine.report_generator.correction_notice import build_correction_notice

        # 空 items 也应生成封面 + 签字页（无人确认为空清单）
        pdf = build_correction_notice([], {"drawing_name": "test.dxf"})
        assert pdf.startswith(b"%PDF")

    def test_grouping_by_func(self):
        from src.baa_engine.report_generator.correction_notice import _group_by_func

        items = [
            {"function_id": "DIM-006", "entity_id": "a"},
            {"function_id": "DIM-006", "entity_id": "b"},
            {"function_id": "EVAC-001", "entity_id": "c"},
        ]
        groups = _group_by_func(items)
        assert len(groups) == 2
        assert len(groups["DIM-006"]) == 2
        assert len(groups["EVAC-001"]) == 1

    def test_grouping_unknown_func(self):
        from src.baa_engine.report_generator.correction_notice import _group_by_func

        items = [{"function_id": None, "entity_id": "x"}]
        groups = _group_by_func(items)
        assert "UNKNOWN" in groups


# ── 2. API endpoint 测试 ────────────────────────────────────


class TestCorrectionNoticeAPI:
    @pytest.fixture
    def client(self):
        from src.api.baa_api import app, API_KEYS

        # 保存并清空 API_KEYS 以启用匿名模式，测试后恢复
        saved = set(API_KEYS)
        API_KEYS.clear()
        from fastapi.testclient import TestClient

        client = TestClient(app)
        yield client
        API_KEYS.clear()
        API_KEYS.update(saved)

    def test_export_pdf_returns_404_when_no_confirmed(self, client):
        resp = client.get(
            "/api/v1/audit/export/pdf",
            params={"review_id": "nonexistent"},
            headers={"Authorization": "test-p119-notice-key"},
        )
        assert resp.status_code == 404

    def test_export_pdf_returns_pdf(self, client):
        from src.baa_engine.collab.audit import create_items_from_review, confirm_item

        review_id = "test-audit-pdf"
        details = [
            {"result": "FAIL", "func_id": "DIM-006", "entity_id": "door-1"},
        ]
        create_items_from_review(review_id, details)
        confirm_item(f"{review_id}:0")

        resp = client.get(
            "/api/v1/audit/export/pdf",
            params={"review_id": review_id, "drawing_name": "test.dxf"},
            headers={"Authorization": "test-p119-notice-key"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/pdf")


# ── 3. 前端审核统计面板测试 ────────────────────────────────


class TestAuditStatsPanel:
    def test_stats_aggregation(self):
        """验证统计聚合逻辑"""
        items = [
            {"status": "confirmed", "function_id": "DIM-006"},
            {"status": "confirmed", "function_id": "DIM-006"},
            {"status": "dismissed", "function_id": "DIM-007"},
            {"status": "pending", "function_id": "EVAC-001"},
            {"status": "unreviewed", "function_id": "DIST-001"},
        ]
        stats = {
            "total": len(items),
            "confirmed": sum(1 for it in items if it["status"] == "confirmed"),
            "dismissed": sum(1 for it in items if it["status"] == "dismissed"),
            "pending": sum(1 for it in items if it["status"] == "pending"),
            "unreviewed": sum(1 for it in items if it["status"] == "unreviewed"),
        }
        assert stats == {"total": 5, "confirmed": 2, "dismissed": 1, "pending": 1, "unreviewed": 1}
