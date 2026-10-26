"""T-C7 扫描件接入：栅格 PDF / 图像 → OCR 文本实体。

链路：
    扫描 PDF → probe（AGPL 隔离子进程判定栅格）→ render-png（隔离渲染 ≥300DPI）
             → tesseract chi_sim OCR（Apache-2.0，主进程内）→ OcrToken 列表

边界说明：
- 仅产出文字内容；扫描件的几何重建（墙线/门窗）不在本任务范围（G11 解阻塞以
  文字识别率为验收口径）。
- OCR 引擎缺失时全部入口返回 None / 空列表，由调用方按"扫描件不可用"降级处理。
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import List, Optional

from src.baa_engine.ocr_text import (
    OcrToken,
    ocr_file,
    tesseract_available,
    ocr_available_reason,
)
from src.baa_engine.parsers.pdf_isolation import (
    probe_pdf_isolated,
    render_pdf_page_isolated,
)

logger = logging.getLogger(__name__)

_RENDER_DPI = 300  # 渲染分辨率高于 200DPI 验收基线，留出预处理余量


def is_scanned_pdf(pdf_path: str, page_index: int = 0) -> Optional[bool]:
    """判定 PDF 页是否为扫描件（无矢量、含栅格大图）。失败返回 None。"""
    probe = probe_pdf_isolated(pdf_path, page_index=page_index)
    if probe is None:
        return None
    return bool(probe.get("is_raster"))


def ocr_scanned_pdf(
    pdf_path: str,
    page_index: int = 0,
    *,
    dpi: int = _RENDER_DPI,
    lang: str = "chi_sim",
) -> Optional[List[OcrToken]]:
    """对扫描 PDF 页执行 OCR。

    返回 OcrToken 列表；非扫描件 / 引擎不可用 / 渲染失败时返回 None。
    """
    if not tesseract_available():
        logger.warning("[T-C7] OCR 不可用：%s", ocr_available_reason())
        return None

    probe = probe_pdf_isolated(pdf_path, page_index=page_index)
    if probe is None:
        logger.warning("[T-C7] PDF 探测失败: %s", pdf_path)
        return None
    if not probe.get("is_raster"):
        logger.info(
            "[T-C7] 矢量页（lines=%s curves=%s），无需 OCR: %s",
            probe.get("lines"),
            probe.get("curves"),
            pdf_path,
        )
        return None

    with tempfile.TemporaryDirectory(prefix="baa_ocr_") as tmp:
        out_png = str(Path(tmp) / f"page{page_index}_{dpi}dpi.png")
        rendered = render_pdf_page_isolated(
            pdf_path, out_png, page_index=page_index, dpi=dpi
        )
        if rendered is None:
            logger.warning("[T-C7] PDF 栅格化失败: %s", pdf_path)
            return None
        logger.info(
            "[T-C7] 扫描页渲染完成 %sx%s@%dDPI: %s",
            rendered.get("width"),
            rendered.get("height"),
            dpi,
            pdf_path,
        )
        return ocr_file(out_png, lang=lang, source_dpi=float(dpi))


def tokens_to_text_entities(tokens: List[OcrToken]) -> List[dict]:
    """将 OCR token 转为审查管道的 TEXT 实体（像素坐标系）。

    扫描件缺少比例尺/单位信息，坐标以像素表示，调用方如需物理尺寸
    应结合比例尺另行换算。
    """
    entities = []
    for i, t in enumerate(tokens):
        entities.append(
            {
                "id": f"ocr-{i}",
                "type": "text",
                "layer": "OCR",
                "bbox": [t.bbox[0], t.bbox[1], t.bbox[2], t.bbox[3]],
                "properties": {
                    "text": t.text,
                    "confidence": t.confidence,
                    "source": "ocr",
                    "line_id": t.line_id,
                },
            }
        )
    return entities
