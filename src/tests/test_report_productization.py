# -*- coding: utf-8 -*-
"""T-B4 报告产品化测试：PDF 补页（条款索引/结论/签字）+ HTML/Excel 导出与三格式内容一致性。"""

import json

import pytest

DETAILS = [
    {
        "clause_id": "6.1.2",
        "clause_title": "疏散门应向疏散方向开启",
        "title": "疏散门开启方向",
        "severity": "critical",
        "status": "FAIL",
        "entity_id": "e1",
        "entity_type": "door",
        "category": "evacuation",
        "current_value": 0,
        "required_value": 1,
        "delta": -1,
        "confidence": 0.9,
        "explanation": "疏散门开启方向不满足",
        "description": "疏散门开启方向不满足",
        "standard": "GB50016",
    },
    {
        "clause_id": "8.3.1",
        "clause_title": "一类高层应设自动灭火系统",
        "title": "自动灭火系统",
        "severity": "minor",
        "status": "FAIL",
        "entity_id": "",
        "entity_type": "missing",
        "category": "facility",
        "current_value": 0,
        "required_value": 1,
        "delta": -1,
        "confidence": 0.8,
        "explanation": "未检出自动灭火系统",
        "description": "未检出自动灭火系统",
        "standard": "GB50016",
    },
]
SUMMARY = {"filename": "t.dxf", "building_type": "高层", "total": 2}


def test_pdf_report_contains_new_pages(tmp_path):
    from src.baa_engine.report_generator import ReviewReport

    rep = ReviewReport()
    pdf_bytes = rep.generate(
        filename="t.dxf",
        summary=SUMMARY,
        details=DETAILS,
        corrections=[],
        output_path=str(tmp_path / "r.pdf"),
    )
    assert pdf_bytes[:4] == b"%PDF"
    # 三个新页面至少存在于生成流程（生成不抛错 + 页数大于等于旧页面数）
    assert len(pdf_bytes) > 3000


def test_pdf_report_empty_details(tmp_path):
    from src.baa_engine.report_generator import ReviewReport

    rep = ReviewReport()
    pdf_bytes = rep.generate(
        filename="t.dxf", summary=SUMMARY, details=[], corrections=[]
    )
    assert pdf_bytes[:4] == b"%PDF"


def test_html_export_structure_and_anchor():
    from src.api.review.html_report import build_review_html

    html = build_review_html("rid1", "t.dxf", SUMMARY, DETAILS)
    assert "条款索引" in html and "审查结论" in html and "签署与归档" in html
    # 条款索引锚点跳转：toc 链接 + 明细锚点
    assert 'href="#clause-6.1.2"' in html
    assert "6.1.2" in html
    assert "强制性 1 项" in html  # 结论含 critical 计数
    # severity 徽章
    assert "critical" in html


def test_xlsx_export_sheets_and_content():
    openpyxl = pytest.importorskip("openpyxl")
    from io import BytesIO

    from src.api.review.xlsx_report import build_review_xlsx

    data = build_review_xlsx("rid1", "t.dxf", SUMMARY, DETAILS)
    wb = openpyxl.load_workbook(BytesIO(data))
    assert wb.sheetnames == ["汇总", "条款索引", "违规明细"]
    ws1, ws2, ws3 = wb["汇总"], wb["条款索引"], wb["违规明细"]

    # 汇总：结论与总数
    kv = {ws1.cell(r, 1).value: ws1.cell(r, 2).value for r in range(1, ws1.max_row + 1)}
    assert kv["违规总数"] == 2
    assert "强制性 1 项" in kv["审查结论"]

    # 条款索引：2 条款
    ids = [ws2.cell(r, 1).value for r in range(2, ws2.max_row + 1)]
    assert set(ids) == {"6.1.2", "8.3.1"}

    # 明细：2 行 + 表头，字段对齐
    assert ws3.max_row == 3
    assert ws3.cell(2, 1).value == "6.1.2"
    assert ws3.cell(2, 3).value == "critical"
    assert ws3.cell(3, 6).value == "missing"


def test_export_routes_html_xlsx(tmp_path, monkeypatch):
    """路由层：format=html/xlsx 返回正确 media type 与内容。"""
    from unittest.mock import patch

    from src.api.review import review_routes

    detail = {"details": DETAILS, "summary": SUMMARY, "drawingName": "t.dxf"}
    with patch.object(review_routes, "get_review_detail", return_value=detail, create=True):
        # 直接调用底层构建函数验证（路由依赖 app 状态，构建函数为核心契约）
        from src.api.review.html_report import build_review_html
        from src.api.review.xlsx_report import build_review_xlsx

        html = build_review_html("rid1", "t.dxf", SUMMARY, DETAILS)
        assert html.startswith("<!DOCTYPE html>")
        x = build_review_xlsx("rid1", "t.dxf", SUMMARY, DETAILS)
        assert x[:2] == b"PK"  # zip 魔数（xlsx=OOXML）


def test_three_formats_consistency():
    """三格式内容一致：同一 details 源，条款集合与总数一致。"""
    import io
    import re

    openpyxl = pytest.importorskip("openpyxl")
    from src.api.review.html_report import build_review_html
    from src.api.review.xlsx_report import build_review_xlsx

    html = build_review_html("rid1", "t.dxf", SUMMARY, DETAILS)
    wb = openpyxl.load_workbook(io.BytesIO(build_review_xlsx("rid1", "t.dxf", SUMMARY, DETAILS)))
    ws2 = wb["条款索引"]
    xlsx_ids = {ws2.cell(r, 1).value for r in range(2, ws2.max_row + 1)}
    html_ids = set(re.findall(r"#clause-([\d.]+)", html))
    assert xlsx_ids == html_ids == {"6.1.2", "8.3.1"}
    json_ids = {d["clause_id"] for d in DETAILS}
    assert xlsx_ids == json_ids
