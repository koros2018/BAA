# -*- coding: utf-8 -*-
"""D3-T4 交付物版本化 + ReportBundle 测试。"""

import json
import zipfile
from pathlib import Path

import pytest


def _write_report_zip(tmp_path: Path, schema_major: int = 1, extra_files: list | None = None) -> Path:
    manifest = {
        "format": "baa-report-bundle",
        "schema_version": f"{schema_major}.0",
        "review_id": "r-test",
        "exported_at": "2026-01-01T00:00:00+00:00",
        "standard_set": "CN-National-v1",
        "dxf_sha256": "abc123",
        "report_schema_version": "1.0",
        "report_version": "v2.5.80",
    }
    out = tmp_path / "report.zip"
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        if extra_files:
            for name, content in extra_files:
                zf.writestr(name, content)
    return out


def test_report_bundle_load_ok(tmp_path):
    from src.sdk import ReportBundle

    zp = _write_report_zip(tmp_path)
    rb = ReportBundle.load(str(zp))
    assert rb.manifest["review_id"] == "r-test"
    assert rb.manifest["schema_version"] == "1.0"
    s = rb.summary()
    assert s["schema_version"] == "1.0"
    assert s["standard_set"] == "CN-National-v1"


def test_report_bundle_version_mismatch(tmp_path):
    from src.sdk import ReportBundle, VersionMismatchError

    zp = _write_report_zip(tmp_path, schema_major=2)
    with pytest.raises(VersionMismatchError, match="schema 主版本不兼容"):
        ReportBundle.load(str(zp))


def test_report_bundle_missing_manifest(tmp_path):
    from src.sdk import ReportBundle, VersionMismatchError

    out = tmp_path / "empty.zip"
    with zipfile.ZipFile(out, "w"):
        pass
    with pytest.raises(VersionMismatchError, match="缺少文件"):
        ReportBundle.load(str(out))


def test_version_mismatch_is_baa_error():
    """VersionMismatchError 继承自 BAAError，可与 KnowledgeBundleError 区分捕获。"""
    from src.sdk import BAAError, VersionMismatchError

    assert issubclass(VersionMismatchError, BAAError)
    # 确保与 KnowledgeBundleError 不同类
    from src.sdk import KnowledgeBundleError

    assert issubclass(VersionMismatchError, BAAError)
    assert VersionMismatchError is not KnowledgeBundleError


def test_report_bundle_sdk_method_exists():
    from src.sdk import BAAClient

    c = BAAClient(api_key="test")
    assert hasattr(c, "export_bundle")
