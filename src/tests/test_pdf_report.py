"""
P69: PDF 报告导出测试

覆盖：
- ReportGenerator 核心 generate()
- 结构化摘要页
- 空详情/空修正建议边界
- 中英双语输出
- review_pdf API 端点（404 + 正常路径）
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# reportlab 为可选依赖；测试环境未安装时跳过，避免阻塞主回归
pytest.importorskip("reportlab")

from fastapi.testclient import TestClient
from src.api.baa_api import app, API_KEYS

os.environ["BAA_API_KEY"] = "test-review-key"
API_KEYS.add("test-review-key")
client = TestClient(app)


# ── 共享测试数据 ─────────────────────────────────────────


MINIMAL_SUMMARY = {
    "building_type": "civil",
    "standard": "GB 50016-2014",
    "total_checks": 100,
    "violations": 2,
    "compliance_rate": 0.98,
    "score": 85.0,
}


MINIMAL_DETAILS = [
    {
        "func_id": "DIM-001",
        "clause_id": "DIM-001",
        "clause_title": "疏散门净宽不应小于0.9m",
        "severity": "major",
        "confidence": 0.85,
        "confidence_tier": "confirmed",
        "category": "防火",
        "explanation": "门洞宽度 0.8m，不满足最小 0.9m 要求",
        "extracted_value": 0.8,
        "required_value": 0.9,
    },
    {
        "func_id": "DIST-001",
        "clause_id": "DIST-001",
        "clause_title": "疏散距离不应超过 40m",
        "severity": "minor",
        "confidence": 0.7,
        "confidence_tier": "suspected",
        "category": "疏散",
        "explanation": "疏散距离 45m，超出 40m 限值",
        "extracted_value": 45.0,
        "required_value": 40.0,
    },
]


MINIMAL_CORRECTIONS = [
    {
        "func_id": "DIM-001",
        "explanation": "建议将门洞宽度调整为 ≥0.9m",
        "severity": "major",
    }
]


# ── ReportGenerator 单元 ──────────────────────────────────


class TestReportGenerator:
    """ReportGenerator 核心方法测试"""

    @pytest.fixture(autouse=True)
    def _reset_font(self):
        """每个测试重置字体注册状态，避免并发污染"""
        import src.baa_engine.report_generator as rg

        original = rg._FONT_REGISTERED
        yield
        rg._FONT_REGISTERED = original

    def _make_generator(self):
        from src.baa_engine.report_generator import ReviewReport

        return ReviewReport()

    def test_generate_minimal(self):
        """最小输入应生成有效 PDF"""
        gen = self._make_generator()
        pdf = gen.generate(
            filename="test.dxf",
            summary=MINIMAL_SUMMARY,
            details=MINIMAL_DETAILS,
            corrections=MINIMAL_CORRECTIONS,
            lang="zh",
        )
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0
        assert pdf[:4] == b"%PDF"

    def test_generate_empty_details(self):
        """空详情（零违规）应生成合法 PDF"""
        gen = self._make_generator()
        pdf = gen.generate(
            filename="clean.dxf",
            summary={"building_type": "civil", "violations": 0},
            details=[],
            corrections=[],
            lang="zh",
        )
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0
        assert pdf[:4] == b"%PDF"

    def test_generate_english(self):
        """英文报告应生成合法 PDF"""
        gen = self._make_generator()
        pdf = gen.generate(
            filename="test.dxf",
            summary=MINIMAL_SUMMARY,
            details=MINIMAL_DETAILS,
            corrections=MINIMAL_CORRECTIONS,
            lang="en",
        )
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0
        assert pdf[:4] == b"%PDF"

    def test_generate_with_structured_summary(self):
        """带结构化摘要应生成含结构化摘要页的 PDF"""
        gen = self._make_generator()
        pdf = gen.generate(
            filename="test.dxf",
            summary=MINIMAL_SUMMARY,
            details=MINIMAL_DETAILS,
            corrections=MINIMAL_CORRECTIONS,
            structured_summary={
                "top_violations": [
                    {
                        "rank": 1,
                        "priority": "P1",
                        "clause_id": "DIM-001",
                        "clause_title": "疏散门净宽",
                        "explanation": "test",
                    }
                ],
                "priority_distribution": {"P0": 0, "P1": 1, "P2": 1},
                "category_distribution": {"防火": {"count": 1, "P0": 0, "P1": 1, "P2": 0}},
                "compliance_actions": [],
            },
            lang="zh",
        )
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0
        assert pdf[:4] == b"%PDF"

    def test_generate_with_diff_report(self):
        """带版本对比报告应生成含 diff 页的 PDF"""
        gen = self._make_generator()
        pdf = gen.generate(
            filename="test.dxf",
            summary=MINIMAL_SUMMARY,
            details=MINIMAL_DETAILS,
            corrections=MINIMAL_CORRECTIONS,
            diff_report={
                "v1_violations": 5,
                "v2_violations": 3,
                "new_violations": 1,
                "resolved_violations": 3,
            },
            lang="zh",
        )
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0
        assert pdf[:4] == b"%PDF"

    def test_generate_returns_bytes(self):
        """generate 返回值类型应为 bytes"""
        gen = self._make_generator()
        pdf = gen.generate(
            filename="test.dxf",
            summary=MINIMAL_SUMMARY,
            details=MINIMAL_DETAILS,
            corrections=MINIMAL_CORRECTIONS,
            lang="zh",
        )
        assert type(pdf) is bytes

    def test_generate_output_path(self):
        """指定 output_path 应写入文件"""
        import tempfile

        gen = self._make_generator()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            out = f.name
        try:
            gen.generate(
                filename="test.dxf",
                summary=MINIMAL_SUMMARY,
                details=MINIMAL_DETAILS,
                corrections=MINIMAL_CORRECTIONS,
                lang="zh",
                output_path=out,
            )
            assert os.path.exists(out)
            assert os.path.getsize(out) > 0
        finally:
            if os.path.exists(out):
                os.remove(out)


# ── /review/pdf API 端点 ─────────────────────────────────


class TestPDFExportEndpoint:
    """/review/pdf API 端点测试"""

    def test_review_pdf_not_found(self):
        """不存在的 review_id 应返回 404"""
        response = client.get(
            "/review/pdf?review_id=nonexistent-uuid",
            headers={"Authorization": "Bearer test-review-key"},
        )
        assert response.status_code == 404
        data = response.json()
        # detail 包装在一层 detail 里
        detail = data.get("detail", data)
        assert detail.get("error_code") == "REVIEW_NOT_FOUND"

    def test_review_pdf_requires_auth(self):
        """未认证请求应被拒绝"""
        response = client.get("/review/pdf?review_id=some-id")
        assert response.status_code in (401, 403, 422)

    def test_review_pdf_invalid_id_format(self):
        """空 review_id 应返回 422"""
        response = client.get(
            "/review/pdf",
            headers={"Authorization": "Bearer test-review-key"},
        )
        assert response.status_code == 422


# ── 端到端：review-from-data → PDF ───────────────────────


class TestPDFEndToEnd:
    """P69 E2E: review-from-data 返回的 task_id 应可被 PDF 端点使用"""

    def test_review_from_data_returns_task_id_at_top_level(self):
        """review-from-data 响应应包含顶层 task_id（P69 修复）"""
        from unittest.mock import patch, MagicMock

        sample_entities = [
            {
                "id": "door_001",
                "type": "door",
                "layer": "E-DOOR",
                "bbox": {"x": 0, "y": 0, "width": 0.9, "height": 2.1},
                "width": 0.9,
                "height": 2.1,
                "center": [0.45, 1.05],
                "attributes": {},
            }
        ]

        with patch("src.api.review.review_routes._get_fr") as mock_fr:
            mock_fr.return_value.list_all = MagicMock(return_value=[])
            response = client.post(
                "/review-from-data",
                json={"entities": sample_entities, "building_type": "civil"},
                headers={"Authorization": "Bearer test-review-key"},
            )

        # 成功或排队超时都合理
        assert response.status_code in (
            200,
            503,
        ), f"review-from-data failed: {response.status_code}: {response.text}"

        if response.status_code == 200:
            data = response.json()
            # P69: task_id 应在顶层，不应只藏在 queue_info 里
            assert "task_id" in data, "task_id should be at top level of response"
            assert data["task_id"] is not None, "task_id should not be None"
            assert isinstance(data["task_id"], str), "task_id should be a string"

            # queue_info.task_id 也应保持一致
            assert "queue_info" in data
            assert data["queue_info"]["task_id"] == data["task_id"]
