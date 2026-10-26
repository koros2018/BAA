"""D2-T3 离线导出路由：POST /exports/{review_id} + GET download."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from src.api.review.review_routes import verify_api_key
from src.baa_engine.export_bundle import get_export_service

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Export"])


def _collect_files(review_id: str):
    """收集 review 相关文件。返回 (files dict, standard_set)。"""
    from src.api.review.review_history import get_review_detail

    detail = get_review_detail(review_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Review {review_id} not found")

    files: dict = {}
    base = Path("src/data/reviews") / review_id
    base.mkdir(parents=True, exist_ok=True)

    # DXF
    dxf_path = base / "source.dxf"
    if not dxf_path.is_file():
        # 尝试从 file_id 路径查找
        fid = detail.get("file_id", "")
        if fid:
            alt = Path("src/data/files") / f"{fid}.dxf"
            if alt.is_file():
                dxf_path = alt
    if dxf_path.is_file():
        files["dxf"] = dxf_path

    # PDF
    try:
        from src.baa_engine.report_generator import ReviewReport

        summary = detail.get("summary", {})
        details = detail.get("details", [])
        corrections = detail.get("corrections", [])
        filename = detail.get("drawingName", "review")
        reporter = ReviewReport()
        pdf_bytes = reporter.generate(
            filename=filename,
            summary=summary,
            details=details,
            corrections=corrections,
            structured_summary={},
            lang="zh",
        )
        pdf_path = base / "report.pdf"
        pdf_path.write_bytes(pdf_bytes)
        files["pdf"] = pdf_path
    except Exception as e:
        _logger.warning(f"[D2-T3] PDF generation failed: {e}")

    # IFC / STEP — 依赖 T3 components，若无则跳过（优雅降级）
    try:
        from src.baa_engine.ifc_export import export_ifc4, ifc_available
        from src.baa_engine.step_export import export_step, step_available

        components = detail.get("components", {}) or {}
        if components and ifc_available():
            ifc_path = base / "model.ifc"
            export_ifc4(components, str(ifc_path))
            if ifc_path.is_file():
                files["ifc"] = ifc_path
        if components and step_available():
            step_path = base / "model.step"
            export_step(components, str(step_path))
            if step_path.is_file():
                files["step"] = step_path
    except Exception as e:
        _logger.warning(f"[D2-T3] IFC/STEP export failed: {e}")

    standard_set = detail.get("standard_set_code", "CN-National-v1") or detail.get("standard", "CN-National-v1")
    return files, standard_set


@router.post("/exports/{review_id}")
async def create_export(review_id: str, api_key: str = Depends(verify_api_key)):
    """创建离线导出 zip 包。"""
    svc = get_export_service()
    try:
        zip_path = svc.get_or_create(review_id, _collect_files)
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"[D2-T3] Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "status": "ok",
        "review_id": review_id,
        "download_url": f"/exports/{review_id}/download",
        "zip_path": str(zip_path),
    }


@router.get("/exports/{review_id}/download")
async def download_export(review_id: str, api_key: str = Depends(verify_api_key)):
    """下载 zip 包。"""
    svc = get_export_service()
    zp = svc.zip_path(review_id)
    if not zp.is_file():
        raise HTTPException(status_code=404, detail=f"Export not found for {review_id}")
    return FileResponse(zp, media_type="application/zip", filename=zp.name)


@router.get("/exports/{review_id}/status")
async def export_status(review_id: str, api_key: str = Depends(verify_api_key)):
    svc = get_export_service()
    return {"review_id": review_id, "ready": svc.exists(review_id)}
