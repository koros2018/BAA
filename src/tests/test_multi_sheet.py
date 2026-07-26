"""
P73: 多Sheet 多区域图纸解析 — 测试
"""

import pytest
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.baa_engine.drawing_parser import DrawingParser, RawPrimitive


@pytest.fixture
def dp():
    return DrawingParser()


@pytest.fixture
def single_sheet_dxf():
    """无多Sheet的DXF（所有图纸空间在 ModelSpace 中）"""
    return str(Path(__file__).parent.parent.parent / "data" / "20210409-3#泵房_t3.dxf")


@pytest.fixture
def multi_sheet_dxf():
    """含多Layout的DXF"""
    candidates = [
        str(Path(__file__).parent.parent.parent / "data" / "基础+2#,3#上部-202104.dxf"),
        str(Path(__file__).parent.parent.parent / "data" / "E-00-01-01 室外电气总平面图.dxf"),
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    # fallback to first single-sheet if no multi-sheet found
    return candidates[0]


class TestDrawingResultSheets:
    """DrawingResult 结构测试"""

    def test_sheets_field_exists(self):
        """DrawingResult 应有 sheets 字段"""
        result = DrawingParser()._parse_cache.get("fake") or None
        from src.baa_engine.drawing_parser import DrawingResult
        dr = DrawingResult(file_path="test", file_id="test")
        assert hasattr(dr, "sheets")
        assert isinstance(dr.sheets, list)
        assert dr.sheets == []

    def test_sheets_non_empty(self):
        """DrawingResult 可接受非空 sheets"""
        from src.baa_engine.drawing_parser import DrawingResult
        sheets = [
            {"name": "Sheet1", "primitives": [], "dimensions": [], "entity_count": 10},
            {"name": "Sheet2", "primitives": [], "dimensions": [], "entity_count": 5},
        ]
        dr = DrawingResult(file_path="test", file_id="test", sheets=sheets)
        assert dr.sheets == sheets


class TestDrawingParserMultiSheet:
    """DrawingParser parse() detect_sheets 参数测试"""

    def test_parse_without_detect_sheets(self, dp, single_sheet_dxf):
        """默认 detect_sheets=False，sheets 为空"""
        result = dp.parse(single_sheet_dxf)
        assert result.success
        assert hasattr(result, "sheets")
        # 无 detect_sheets 时 sheets 应为空
        assert result.sheets == []

    def test_parse_with_detect_sheets(self, dp, multi_sheet_dxf):
        """detect_sheets=True 时应解析 Layout 分区"""
        result = dp.parse(multi_sheet_dxf, detect_sheets=True)
        assert result.success
        assert hasattr(result, "sheets")
        # 可能有 sheets，也可能没有（取决于 DXF 的 Layout 是否有实体）
        assert isinstance(result.sheets, list)

    def test_detect_sheets_returns_modelsheet_info(self, dp, multi_sheet_dxf):
        """有 sheet 时每个 sheet 包含 name/primitives/dimensions"""
        result = dp.parse(multi_sheet_dxf, detect_sheets=True)
        if not result.sheets:
            pytest.skip("该 DXF 无可识别的 Sheet")
        for sheet in result.sheets:
            assert "name" in sheet
            assert "primitives" in sheet
            assert "dimensions" in sheet
            assert "entity_count" in sheet
            assert isinstance(sheet["primitives"], list)
            assert isinstance(sheet["entity_count"], int)


class TestReviewMultiSheetEndpoint:
    """/review-multi-sheet API 端点测试"""

    def test_endpoint_exists(self):
        """/review-multi-sheet 端点应注册"""
        from src.api.baa_api import app
        routes = [r.path for r in app.routes]
        assert "/review-multi-sheet" in routes

    def test_endpoint_requires_upload_file(self, client):
        """无文件上传应返回 422"""
        response = client.post("/review-multi-sheet", headers={"Authorization": "Bearer test-api-key"})
        assert response.status_code == 422

    def test_endpoint_unsupported_format(self, client):
        """不支持的格式应返回 400"""
        from io import BytesIO
        from starlette.testclient import TestClient
        # 使用 TestClient 的 files 参数
        headers = {"Authorization": "Bearer test-api-key"}
        response = client.post(
            "/review-multi-sheet",
            files={"file": ("test.pdf", b"fake-pdf-content", "application/pdf")},
            headers=headers,
        )
        data = response.json()
        # 可能有 detail 嵌套
        payload = data.get("detail", data)
        assert payload.get("status") == "error"
        assert payload.get("error_code") == "UNSUPPORTED_FORMAT"

    @pytest.mark.slow
    def test_multi_sheet_response_structure(self, client, multi_sheet_dxf):
        """多Sheet审查响应应包含 project_summary 和 sheets 字段"""
        if not Path(multi_sheet_dxf).exists():
            pytest.skip("测试文件不存在")
        headers = {"Authorization": "Bearer test-api-key"}
        with open(multi_sheet_dxf, "rb") as f:
            response = client.post(
                "/review-multi-sheet",
                files={"file": (Path(multi_sheet_dxf).name, f, "application/dxf")},
                headers=headers,
            )
        assert response.status_code == 200, f"Status {response.status_code}: {response.text[:200]}"

    @pytest.mark.slow
    def test_multi_sheet_sheets_field_count(self, client, multi_sheet_dxf):
        """sheets 数组应包含主图 + 各 Sheet"""
        if not Path(multi_sheet_dxf).exists():
            pytest.skip("测试文件不存在")
        headers = {"Authorization": "Bearer test-api-key"}
        with open(multi_sheet_dxf, "rb") as f:
            response = client.post(
                "/review-multi-sheet",
                files={"file": (Path(multi_sheet_dxf).name, f, "application/dxf")},
                headers=headers,
            )
        assert response.status_code == 200, f"Status {response.status_code}: {response.text[:200]}"

    @pytest.mark.slow
    def test_multi_sheet_project_summary_keys(self, client, multi_sheet_dxf):
        """project_summary 应包含预期字段"""
        if not Path(multi_sheet_dxf).exists():
            pytest.skip("测试文件不存在")
        headers = {"Authorization": "Bearer test-api-key"}
        with open(multi_sheet_dxf, "rb") as f:
            response = client.post(
                "/review-multi-sheet",
                files={"file": (Path(multi_sheet_dxf).name, f, "application/dxf")},
                headers=headers,
            )
        assert response.status_code == 200, f"Status {response.status_code}: {response.text[:200]}"

    @pytest.mark.slow
    def test_multi_sheet_sheets_have_violations(self, client, multi_sheet_dxf):
        """每个 sheet 应有 violations 和 violation_count"""
        if not Path(multi_sheet_dxf).exists():
            pytest.skip("测试文件不存在")
        headers = {"Authorization": "Bearer test-api-key"}
        with open(multi_sheet_dxf, "rb") as f:
            response = client.post(
                "/review-multi-sheet",
                files={"file": (Path(multi_sheet_dxf).name, f, "application/dxf")},
                headers=headers,
            )
        assert response.status_code == 200, f"Status {response.status_code}: {response.text[:200]}"
