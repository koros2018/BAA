"""T-C6 知识库开放验收单测：一键导出包 + schema 版本化 + SDK 离线加载。

覆盖：
- 一键导出（zip 结构、manifest 计数、sha256）
- schema 契约（原子函数/规范条文字段集合随包固化）
- SDK KnowledgeBundle 加载、查询、完整性/版本兼容校验
- 示例脚本可执行（10 分钟跑通路径的可验证子集）
"""

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


# ── 一键导出 ──────────────────────────────────────────────


def test_one_click_export_zip(tmp_path):
    from src.baa_engine.knowledge import BUNDLE_FILES, write_bundle

    out = write_bundle(tmp_path / "kb.zip", quiet=True)

    assert out.exists() and out.suffix == ".zip"
    with zipfile.ZipFile(out) as zf:
        assert set(zf.namelist()) == set(BUNDLE_FILES)
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        funcs = json.loads(zf.read("functions.json").decode("utf-8"))
        specs = json.loads(zf.read("specs.json").decode("utf-8"))

        assert manifest["format"] == "baa-knowledge-bundle"
        assert manifest["schema_version"].count(".") == 1
        assert manifest["counts"]["functions"] == len(funcs) > 0
        assert manifest["counts"]["specs"] == len(specs) > 0
        assert len(manifest["standards"]) == manifest["counts"]["standards"] >= 1

        # 每个数据文件的 sha256 与 manifest 一致
        for name, meta in manifest["files"].items():
            assert hashlib.sha256(zf.read(name)).hexdigest() == meta["sha256"]


def test_export_to_directory_uses_versioned_name(tmp_path):
    from src.baa_engine.knowledge import KB_VERSION, write_bundle

    out = write_bundle(tmp_path, quiet=True)
    assert out == tmp_path / f"baa_knowledge_v{KB_VERSION}.zip"
    assert out.exists()


def test_cli_export_and_verify(tmp_path):
    """CLI 一键导出 + 产物自校验（read_bundle_manifest 校验 sha256 与主版本）。"""
    from src.baa_engine.knowledge import read_bundle_manifest

    out = tmp_path / "cli.zip"
    proc = subprocess.run(
        [sys.executable, "-m", "src.baa_engine.knowledge", "-o", str(out), "--quiet"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    assert str(out) in proc.stdout

    manifest = read_bundle_manifest(out)
    assert manifest["counts"]["functions"] > 0


def test_schema_contract_fields():
    """schema 契约：包内每个条目必须含对外承诺字段（字段缺失=不兼容变更）。"""
    from src.baa_engine.knowledge import build_bundle_payloads

    payloads = build_bundle_payloads()
    funcs = json.loads(payloads["functions.json"])
    specs = json.loads(payloads["specs.json"])
    versions = json.loads(payloads["versions.json"])

    func_fields = {
        "func_id",
        "name",
        "description",
        "category",
        "clause_id",
        "target_entities",
        "operator",
        "threshold",
        "unit",
        "depends_on",
    }
    spec_fields = {
        "clause_id",
        "standard",
        "title",
        "text",
        "level",
        "func_id",
        "category",
        "params",
    }
    assert func_fields <= set(funcs[0]), func_fields - set(funcs[0])
    assert spec_fields <= set(specs[0]), spec_fields - set(specs[0])
    assert all(func_fields <= set(f) for f in funcs)
    assert all(spec_fields <= set(s) for s in specs)

    assert set(versions) == {"standards", "versions", "change_logs"}
    assert versions["standards"]


def test_missing_file_rejected(tmp_path):
    from src.baa_engine.knowledge import write_bundle, read_bundle_manifest

    src_zip = write_bundle(tmp_path / "ok.zip", quiet=True)
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(src_zip) as src, zipfile.ZipFile(broken, "w") as dst:
        for name in src.namelist():
            if name != "specs.json":
                dst.writestr(name, src.read(name))

    with pytest.raises(ValueError, match="缺少文件"):
        read_bundle_manifest(broken)


# ── SDK 离线加载 ──────────────────────────────────────────


@pytest.fixture
def bundle_path(tmp_path):
    from src.baa_engine.knowledge import write_bundle

    return write_bundle(tmp_path / "kb.zip", quiet=True)


def test_sdk_load_and_query(bundle_path):
    from src.sdk import KnowledgeBundle

    kb = KnowledgeBundle.load(bundle_path)
    info = kb.summary()
    assert info["format"] == "baa-knowledge-bundle"
    assert info["counts"]["functions"] == len(kb.functions)
    assert len(info["standards"]) == info["counts"]["standards"]

    sample = kb.functions[0]
    assert kb.function(sample["func_id"])["name"] == sample["name"]
    assert kb.function("__不存在__") is None

    grouped = kb.specs_by_standard()
    assert sum(len(v) for v in grouped.values()) == len(kb.specs)


def test_sdk_rejects_tampered_bundle(bundle_path, tmp_path):
    """篡改内容后 sha256 不匹配 → 拒绝加载（防止知识库被静默改写）。"""
    from src.sdk import KnowledgeBundle, KnowledgeBundleError

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(bundle_path) as src, zipfile.ZipFile(tampered, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "functions.json":
                data = json.dumps([]).encode("utf-8")
            dst.writestr(name, data)

    with pytest.raises(KnowledgeBundleError, match="校验和不匹配"):
        KnowledgeBundle.load(tampered)


def test_sdk_rejects_incompatible_schema_major(bundle_path, tmp_path):
    """schema 主版本不兼容 → 拒绝加载（版本化契约的强制点）。"""
    from src.sdk import KnowledgeBundle, KnowledgeBundleError

    future = tmp_path / "future.zip"
    with zipfile.ZipFile(bundle_path) as src, zipfile.ZipFile(future, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "manifest.json":
                manifest = json.loads(data)
                manifest["schema_version"] = "2.0"
                data = json.dumps(manifest).encode("utf-8")
            dst.writestr(name, data)

    with pytest.raises(KnowledgeBundleError, match="schema 主版本不兼容"):
        KnowledgeBundle.load(future)


def test_sdk_rejects_wrong_format(bundle_path, tmp_path):
    from src.sdk import KnowledgeBundle, KnowledgeBundleError

    other = tmp_path / "other.zip"
    with zipfile.ZipFile(bundle_path) as src, zipfile.ZipFile(other, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "manifest.json":
                manifest = json.loads(data)
                manifest["format"] = "something-else"
                data = json.dumps(manifest).encode("utf-8")
            dst.writestr(name, data)

    with pytest.raises(KnowledgeBundleError, match="非 BAA 知识库包"):
        KnowledgeBundle.load(other)


def test_sdk_missing_bundle():
    from src.sdk import KnowledgeBundle, KnowledgeBundleError

    with pytest.raises(KnowledgeBundleError, match="不存在"):
        KnowledgeBundle.load("__no_such_bundle__.zip")


# ── 示例脚本（10 分钟跑通路径）─────────────────────────────


def test_offline_example_runs_end_to_end(tmp_path):
    """示例脚本从零导出并跑通（等价于新用户 clone 后的第一条命令）。"""
    proc = subprocess.run(
        [
            sys.executable,
            "src/sdk/examples/quickstart_offline.py",
            str(tmp_path / "kb.zip"),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr
    assert "[OK] 离线示例跑通" in proc.stdout
    assert "原子函数" in proc.stdout


# ── SDK 打包元数据（防回退到不可构建配置）──────────────────


def test_sdk_pyproject_is_installable():
    """pyproject 配置必须可构建：合法 backend + 包目录映射 + 版本与 __version__ 一致。"""
    tomllib = pytest.importorskip("tomllib", reason="Python 3.11+ 才有 tomllib")
    cfg = tomllib.loads((ROOT / "src" / "sdk" / "pyproject.toml").read_text(encoding="utf-8"))

    assert cfg["build-system"]["build-backend"] == "setuptools.build_meta"
    assert "py-modules" not in cfg["tool"]["setuptools"], "py-modules 与实际目录结构不匹配"
    assert cfg["tool"]["setuptools"]["packages"] == ["baa_sdk"]
    assert cfg["tool"]["setuptools"]["package-dir"]["baa_sdk"] == "."
    # 零必需依赖（httpx 为 optional），避免引用不存在的 requirements.txt
    assert cfg["project"]["dependencies"] == []
    assert "dynamic" not in cfg["project"]

    from src.sdk import __version__

    assert cfg["project"]["version"] == __version__
