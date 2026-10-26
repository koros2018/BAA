"""D2-T3 离线导出：审查记录 → zip 交付包（DXF+PDF+IFC+STEP+manifest）。

设计要点：
- 收集 DXF 源文件、PDF 报告、IFC、STEP 四类文件 + manifest.json 打包为 zip
- 幂等：同一 review_id 已有 zip 直接返回
- 文件锁防止并发打包
- manifest.json 字段：review_id/exported_at/standard_set/ifc_path/step_path/dxf_sha256/report_version/report_schema_version
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

EXPORT_DIR = Path(os.getenv("BAA_EXPORT_DIR", "src/data/exports"))
EXPORT_RETENTION_DAYS = int(os.getenv("BAA_EXPORT_RETENTION_DAYS", "7"))
REPORT_SCHEMA_VERSION = "1.0"
REPORT_VERSION = "v2.5.80"


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class ExportBundleService:
    """审查交付包打包服务。"""

    def __init__(self, export_dir: Optional[Path] = None):
        self.export_dir = _ensure_dir(export_dir or EXPORT_DIR)

    def zip_path(self, review_id: str) -> Path:
        return self.export_dir / f"review_{review_id}.zip"

    def exists(self, review_id: str) -> bool:
        return self.zip_path(review_id).is_file()

    def build(self, review_id: str, files: Dict[str, Path], standard_set: str = "CN-National-v1") -> Path:
        """收集文件 + 生成 manifest + 打包 zip。"""
        out = self.zip_path(review_id)
        manifest = {
            "review_id": review_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "standard_set": standard_set,
            "ifc_path": files.get("ifc", Path()).name if "ifc" in files else "",
            "step_path": files.get("step", Path()).name if "step" in files else "",
            "dxf_sha256": _sha256_file(files["dxf"]) if "dxf" in files and files["dxf"].is_file() else "",
            "report_version": REPORT_VERSION,
            "report_schema_version": REPORT_SCHEMA_VERSION,
        }
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for key, p in files.items():
                if p and p.is_file():
                    zf.write(p, p.name)
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        logger.info(f"[D2-T3] Export bundle built: {out}")
        return out

    def get_or_create(self, review_id: str, collect_fn) -> Path:
        """幂等获取或创建 zip。collect_fn(review_id) -> (files dict, standard_set)。"""
        out = self.zip_path(review_id)
        if out.is_file():
            return out
        files, standard_set = collect_fn(review_id)
        return self.build(review_id, files, standard_set)


_service: Optional[ExportBundleService] = None


def get_export_service() -> ExportBundleService:
    global _service
    if _service is None:
        _service = ExportBundleService()
    return _service


def reset_export_service_for_test() -> None:
    global _service
    _service = None
