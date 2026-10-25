"""T-C6 知识库开放：原子函数/规范 schema 版本化 + 一键导出知识库包。

导出包（zip）结构：
    manifest.json   包元数据：format / schema_version / kb_version / 生成时间 /
                    条目计数 / 每个数据文件的 sha256
    functions.json  原子函数清单（含分类、条款关联、阈值、目标实体、依赖）
    specs.json      规范条文清单（含标准、层级、关联原子函数、阈值）
    versions.json   规范版本元数据 + 版本间变更日志

用法（一键导出）：
    python -m src.baa_engine.knowledge --output dist/baa_knowledge.zip
    python -m src.baa_engine.knowledge --output dist --quiet

schema 版本语义：
    schema_version 主版本变更 = 不兼容（SDK 拒绝加载），次版本 = 向后兼容新增。
    SDK 侧 `baa_sdk.KnowledgeBundle` 按主版本做兼容校验。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 版本常量 ──────────────────────────────────────────────

KB_FORMAT = "baa-knowledge-bundle"
KB_SCHEMA_VERSION = "1.0"  # 包结构与字段契约版本（主版本不兼容变更）
KB_VERSION = "1.0.0"  # 知识库内容版本（原子函数 + 规范条文集合）

BUNDLE_FILES = ("manifest.json", "functions.json", "specs.json", "versions.json")


# ── 序列化 ────────────────────────────────────────────────


def _func_to_dict(func: Any) -> Dict[str, Any]:
    """原子函数 → 可序列化字典（字段与 /api/v1/functions 保持一致）。"""
    category = getattr(func, "category", None)
    return {
        "func_id": func.func_id,
        "name": func.name,
        "description": func.description,
        "category": category.value if hasattr(category, "value") else str(category),
        "clause_id": func.clause_id,
        "target_entities": list(func.target_entities),
        "operator": func.operator,
        "threshold": func.threshold,
        "unit": func.unit,
        "depends_on": list(func.depends_on),
        "requires_global_context": bool(getattr(func, "requires_global_context", False)),
    }


def _clause_to_dict(clause: Any) -> Dict[str, Any]:
    """规范条文 → 可序列化字典（含可选 threshold 结构化阈值）。"""
    data: Dict[str, Any] = {
        "clause_id": clause.clause_id,
        "standard": clause.standard,
        "title": clause.title,
        "text": clause.text,
        "level": clause.level,
        "func_id": clause.func_id,
        "category": clause.category,
        "params": clause.params,
    }
    th = getattr(clause, "threshold", None)
    if th is not None:
        data["threshold"] = {
            "value": th.value,
            "unit": th.unit,
            "operator": th.operator,
            "building_types": th.building_types,
        }
    return data


def _versions_payload() -> Dict[str, Any]:
    """规范版本元数据 + 变更日志。"""
    from src.baa_engine.spec_data.versioning import VersionManager

    manager = VersionManager()
    return {
        "standards": manager.list_supported_standards(),
        "versions": manager.list_versions(),
        "change_logs": {
            "GB 50016 2014→2025": manager.get_change_log("GB 50016", "2014", "2025"),
            "NFPA 101 2021→2024": manager.get_change_log("NFPA 101", "2021", "2024"),
        },
    }


def _dumps(obj: Any) -> bytes:
    """确定性 JSON 序列化（键排序、保留中文、2 空格缩进）。"""
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── 导出 ──────────────────────────────────────────────────


def build_bundle_payloads() -> Dict[str, bytes]:
    """构建导出包内全部文件内容（不落盘，便于测试与流式分发）。

    Returns:
        {文件名: 字节内容}，键顺序与 BUNDLE_FILES 一致。
    """
    from src.baa_engine.atomic_functions import FuncRegistry
    from src.baa_engine.spec_repository import SpecRepository

    funcs = [_func_to_dict(f) for f in FuncRegistry().list_all()]
    specs = [_clause_to_dict(c) for c in SpecRepository().list_all()]
    versions = _versions_payload()

    functions_bytes = _dumps(funcs)
    specs_bytes = _dumps(specs)
    versions_bytes = _dumps(versions)

    standards = sorted({s["standard"] for s in specs})
    manifest = {
        "format": KB_FORMAT,
        "schema_version": KB_SCHEMA_VERSION,
        "kb_version": KB_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "src.baa_engine.knowledge",
        "counts": {
            "functions": len(funcs),
            "specs": len(specs),
            "standards": len(standards),
        },
        "standards": standards,
        "files": {
            "functions.json": {
                "sha256": _sha256(functions_bytes),
                "bytes": len(functions_bytes),
            },
            "specs.json": {"sha256": _sha256(specs_bytes), "bytes": len(specs_bytes)},
            "versions.json": {"sha256": _sha256(versions_bytes), "bytes": len(versions_bytes)},
        },
    }

    return {
        "manifest.json": _dumps(manifest),
        "functions.json": functions_bytes,
        "specs.json": specs_bytes,
        "versions.json": versions_bytes,
    }


def write_bundle(output: str | Path, quiet: bool = False) -> Path:
    """一键导出知识库包。

    Args:
        output: 输出 zip 路径；若为目录或带路径分隔符的目录，则自动以
            ``baa_knowledge_v{KB_VERSION}.zip`` 命名。

    Returns:
        实际写入的 zip 路径。
    """
    payloads = build_bundle_payloads()

    out = Path(output)
    if out.is_dir() or out.suffix.lower() != ".zip":
        out.mkdir(parents=True, exist_ok=True)
        out = out / f"baa_knowledge_v{KB_VERSION}.zip"
    else:
        out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in BUNDLE_FILES:
            zf.writestr(name, payloads[name])

    if not quiet:
        manifest = json.loads(payloads["manifest.json"].decode("utf-8"))
        logger.info(
            "[T-C6] 知识库包已导出 %s（schema=%s kb=%s functions=%d specs=%d standards=%d）",
            out,
            manifest["schema_version"],
            manifest["kb_version"],
            manifest["counts"]["functions"],
            manifest["counts"]["specs"],
            manifest["counts"]["standards"],
        )
    return out


def read_bundle_manifest(path: str | Path) -> Dict[str, Any]:
    """读取并校验包完整性（manifest 与文件 sha256 一致），返回 manifest。"""
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        missing = set(BUNDLE_FILES) - names
        if missing:
            raise ValueError(f"知识库包缺少文件: {sorted(missing)}")
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        if manifest.get("format") != KB_FORMAT:
            raise ValueError(f"非 BAA 知识库包: format={manifest.get('format')}")
        for name, meta in manifest.get("files", {}).items():
            actual = _sha256(zf.read(name))
            if actual != meta["sha256"]:
                raise ValueError(f"{name} 校验和不匹配（包已损坏或被篡改）")
        major = str(manifest.get("schema_version", "")).split(".")[0]
        supported = KB_SCHEMA_VERSION.split(".")[0]
        if major != supported:
            raise ValueError(
                f"schema 主版本不兼容: 包={manifest.get('schema_version')} 支持={KB_SCHEMA_VERSION}"
            )
    return manifest


# ── CLI ───────────────────────────────────────────────────


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.baa_engine.knowledge",
        description="一键导出 BAA 知识库包（原子函数 + 规范条文 + 版本元数据）",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="dist/baa_knowledge.zip",
        help="输出 zip 路径或目录（默认 dist/baa_knowledge.zip）",
    )
    parser.add_argument("--quiet", action="store_true", help="静默模式（只输出路径）")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        out = write_bundle(args.output, quiet=args.quiet)
        manifest = read_bundle_manifest(out)
    except Exception as e:  # 导出失败需明确失败退出码，供 CI/脚本判定
        logger.error("[T-C6] 知识库导出失败: %s", e)
        return 1

    if args.quiet:
        print(out)
    else:
        print(f"输出: {out}")
        print(f"schema_version: {manifest['schema_version']}  kb_version: {manifest['kb_version']}")
        print(
            "计数: functions={functions} specs={specs} standards={standards}".format(
                **manifest["counts"]
            )
        )
        print(f"大小: {out.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
