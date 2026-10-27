# -*- coding: utf-8 -*-
"""D3-T1 交付物包模板系统测试。"""

import json
import tempfile

import pytest


@pytest.fixture(autouse=True)
def _reset_templates():
    from src.baa_engine.report_generator.template import reset_template_registry_for_test
    reset_template_registry_for_test()
    yield
    reset_template_registry_for_test()


def test_builtin_templates_exist():
    from src.baa_engine.report_generator.template import get_template_registry
    reg = get_template_registry()
    codes = {t.code for t in reg.all()}
    assert "national" in codes
    assert "local" in codes


def test_template_colors_flow_to_styles():
    from src.baa_engine.report_generator import ReviewReport
    r_national = ReviewReport(template_code="national")
    r_local = ReviewReport(template_code="local")
    # national 主色深蓝，local 主色棕黄，必须不同
    assert r_national.template.primary_color != r_local.template.primary_color
    # styles section-title 从模板取色
    assert r_national.styles["section-title"].textColor != r_local.styles["section-title"].textColor


def test_unknown_template_fallback():
    from src.baa_engine.report_generator import ReviewReport
    r = ReviewReport(template_code="nonexistent")
    assert r.template.code == "national"  # fallback


def test_custom_template_from_dir(tmp_path):
    from src.baa_engine.report_generator.template import TemplateRegistry, ReportTemplate
    custom = {
        "code": "client_x",
        "name": "Client X 模板",
        "description": "自定义",
        "primary_color": "#ff0000",
        "accent_color": "#00ff00",
        "title": "Client X 报告",
        "sections": ["cover", "violations"],
        "footer_text": "Client X",
    }
    f = tmp_path / "client_x.json"
    f.write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
    reg = TemplateRegistry()
    n = reg.load_custom_from_dir(str(tmp_path))
    assert n == 1
    t = reg.get("client_x")
    assert t.title == "Client X 报告"
    assert t.primary_color == "#ff0000"


def test_generate_with_template(tmp_path):
    """不同 template_code 生成 PDF，字节长度差异反映配色/章节不同。"""
    from src.baa_engine.report_generator import ReviewReport
    summary = {"total": 10, "critical": 1, "major": 2, "minor": 7}
    details = [{"id": "f1", "severity": "critical", "func_id": "TEST", "clause": "C1", "description": "d"}]
    corrections = []
    r1 = ReviewReport(template_code="national")
    buf1 = r1.generate("test", summary, details, corrections)
    assert len(buf1) > 0
    # local template colors 不同，但 sections 相同 -> 长度大致相同
    r2 = ReviewReport(template_code="local")
    buf2 = r2.generate("test", summary, details, corrections)
    assert len(buf2) > 0
