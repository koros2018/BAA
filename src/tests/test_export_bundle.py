# -*- coding: utf-8 -*-
"""D2-T3 离线导出测试：zip 打包 + manifest + 幂等 + SDK export_bundle。"""

import hashlib
import io
import json
import os
import tempfile
import zipfile

import pytest


@pytest.fixture(autouse=True)
def _reset_export_service():
    from src.baa_engine.export_bundle import reset_export_service_for_test

    reset_export_service_for_test()
    yield
    reset_export_service_for_test()


def test_export_bundle_build_zip(tmp_path):
    """build() 产出包含 manifest.json 且 zip 可读。"""
    from src.baa_engine.export_bundle import ExportBundleService

    svc = ExportBundleService(export_dir=tmp_path)
    dxf = tmp_path / "source.dxf"
    dxf.write_text("0\nSECTION\n0\nENDSEC\n0\nEOF\n", encoding="utf-8")
    files = {"dxf": dxf}
    zp = svc.build("r1", files, standard_set="CN-Shanghai-v1")
    assert zp.is_file()
    with zipfile.ZipFile(zp) as zf:
        names = zf.namelist()
        assert "source.dxf" in names
        assert "manifest.json" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["review_id"] == "r1"
        assert manifest["standard_set"] == "CN-Shanghai-v1"
        assert manifest["dxf_sha256"] == hashlib.sha256(dxf.read_bytes()).hexdigest()


def test_export_bundle_idempotent(tmp_path):
    """get_or_create 对同一 review_id 返回同一路径。"""
    from src.baa_engine.export_bundle import ExportBundleService

    svc = ExportBundleService(export_dir=tmp_path)
    dxf = tmp_path / "source.dxf"
    dxf.write_text("0\nEOF\n", encoding="utf-8")

    def collect(rid):
        return ({"dxf": dxf}, "CN-National-v1")

    p1 = svc.get_or_create("r2", collect)
    p2 = svc.get_or_create("r2", collect)
    assert p1 == p2
    assert p1.is_file()


def test_export_bundle_manifest_fields(tmp_path):
    """manifest.json 包含 8 个必需字段。"""
    from src.baa_engine.export_bundle import ExportBundleService

    svc = ExportBundleService(export_dir=tmp_path)
    dxf = tmp_path / "source.dxf"
    dxf.write_text("0\nEOF\n", encoding="utf-8")
    zp = svc.build("r3", {"dxf": dxf})
    with zipfile.ZipFile(zp) as zf:
        m = json.loads(zf.read("manifest.json"))
    required = {"review_id", "exported_at", "standard_set", "ifc_path", "step_path", "dxf_sha256", "report_version", "report_schema_version"}
    assert required.issubset(m.keys())


def test_export_service_singleton_reset():
    """reset_export_service_for_test 清空单例。"""
    from src.baa_engine.export_bundle import get_export_service, reset_export_service_for_test

    s1 = get_export_service()
    reset_export_service_for_test()
    s2 = get_export_service()
    assert s1 is not s2
