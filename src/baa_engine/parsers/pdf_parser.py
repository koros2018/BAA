"""
P99: PDF 矢量解析器

从矢量 PDF（92% 业务图纸）提取线条/弧线/文字，转为 ezdxf 内存文档，
然后喂给现有 DrawingParser 走完整审查管道。
跳过 YOLO / 硬转 DXF 方案。
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Optional

import ezdxf
import fitz

# PDF 点到 mm 的转换（1 pt = 25.4/72 mm）
_PT_TO_MM = 25.4 / 72


def _extract_scale(doc: fitz.Document) -> int:
    """从 PDF 全文搜索比例尺标注，返回比例分母（如 1:150 → 150）"""
    patterns = [
        r"比例[：:]?\s*1[：:]?([0-9]+)",  # 比例 1:150
        r"1[：:]([0-9]+)",  # 1:150 直接出现
        r"SCALE[：:]?\s*1[：:]?([0-9]+)",
    ]
    all_text = ""
    for page in doc:
        all_text += page.get_text()
    for pat in patterns:
        m = re.search(pat, all_text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return 1  # 未找到比例尺，默认 1:1


def pdf_to_dxf(
    pdf_path: str,
    page_index: int = 0,
    scale: Optional[int] = None,
) -> dict:
    """PDF → DXF 文件路径，含比例尺恢复

    核心流程：
    1. PyMuPDF 打开 PDF，提取全文搜索比例尺
    2. 逐 path 展开为线段 / 弧线 / 矩形 / 贝塞尔，按 pt→mm×比例尺 缩放
    3. 写入 ezdxf 内存文档
    4. 导出 DXF 文件供 DrawingParser 消费

    参数:
        pdf_path: 输入 PDF 路径
        page_index: 目标页（默认第 1 页）
        scale: 强制比例尺分母（如 150），None 则自动从 PDF 文字提取

    返回: {"dxf_path", "lines", "arcs", "text", "scale", "pt_to_mm_scale"}
    """
    doc = fitz.open(pdf_path)
    page = doc[page_index]

    if scale is None:
        scale = _extract_scale(doc)
    # 缩放因子：PDF pt → mm × 比例尺
    pt_to_mm_scale = _PT_TO_MM * scale

    pdf_path = Path(pdf_path)
    dxf_path = pdf_path.with_suffix(".pdf2dxf.dxf")

    # ── 新建 ezdxf 文档 ──
    dxf = ezdxf.new("R2010")
    msp = dxf.modelspace()

    # 图层：线条走 "lines"，文字走 "text"，弧线走 "arcs"
    dxf.layers.add(name="lines")
    dxf.layers.add(name="text")
    dxf.layers.add(name="arcs")
    dxf.layers.add(name="circles")
    dxf.layers.add(name="hatches")

    line_count = 0
    arc_count = 0
    text_count = 0
    circle_count = 0
    hatch_count = 0

    # ── 1. 提取矢量路径 ──
    drawings = page.get_drawings()
    for drawing in drawings:
        items = drawing["items"]
        stroke_width = drawing.get("width") or 0.5

        for item in items:
            cmd = item[0]

            if cmd == "l":  # 线段
                p1 = item[1]
                p2 = item[2]
                msp.add_line(
                    (p1.x * pt_to_mm_scale, p1.y * pt_to_mm_scale),
                    (p2.x * pt_to_mm_scale, p2.y * pt_to_mm_scale),
                    dxfattribs={"layer": "lines"},
                )
                line_count += 1

            elif cmd == "c":  # 三次贝塞尔 → 拆成多条线段
                p1 = item[1]
                p2 = item[2]
                p3 = item[3]
                p4 = item[4]
                _bezier_to_lines(msp, p1, p2, p3, p4, steps=8, scale=pt_to_mm_scale)
                line_count += 8

            elif cmd == "a":  # 圆弧
                center = item[1]
                radius = float(item[2])
                start = float(item[3])
                end = float(item[4])
                if radius > 0.001:
                    msp.add_arc(
                        (center.x * pt_to_mm_scale, center.y * pt_to_mm_scale),
                        radius * pt_to_mm_scale,
                        start,
                        end,
                        dxfattribs={"layer": "arcs"},
                    )
                    arc_count += 1

            elif cmd == "re":  # 矩形 → 4 条线段
                rect = item[1]
                x0, y0 = rect.x0, rect.y0
                x1, y1 = rect.x1, rect.y1
                # 跳过 degenerate rects
                if abs(x1 - x0) > 0.01 and abs(y1 - y0) > 0.01:
                    sx = x0 * pt_to_mm_scale
                    sy = y0 * pt_to_mm_scale
                    ex = x1 * pt_to_mm_scale
                    ey = y1 * pt_to_mm_scale
                    msp.add_line((sx, sy), (ex, sy), dxfattribs={"layer": "lines"})
                    msp.add_line((ex, sy), (ex, ey), dxfattribs={"layer": "lines"})
                    msp.add_line((ex, ey), (sx, ey), dxfattribs={"layer": "lines"})
                    msp.add_line((sx, ey), (sx, sy), dxfattribs={"layer": "lines"})
                    line_count += 4

    # ── 2. 提取文字 ──
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line_obj in block.get("lines", []):
            for span in line_obj.get("spans", []):
                txt = span.get("text", "").strip()
                if not txt:
                    continue
                bbox = span.get("bbox", [0, 0, 0, 0])
                x = bbox[0]
                y = bbox[1]
                height = span.get("size", 12)
                txt_obj = msp.add_text(
                    txt,
                    height=height * pt_to_mm_scale,
                    dxfattribs={"layer": "text"},
                )
                txt_obj.dxf.insert = (x * pt_to_mm_scale, (y + height) * pt_to_mm_scale)
                text_count += 1

    doc.close()

    # ── 3. 写 DXF ──
    dxf.saveas(str(dxf_path))

    return {
        "dxf_path": str(dxf_path),
        "lines": line_count,
        "arcs": arc_count,
        "text": text_count,
        "scale": scale,
        "pt_to_mm_scale": round(pt_to_mm_scale, 4),
    }


def _bezier_to_lines(msp, p1, p2, p3, p4, steps: int = 8, scale: float = 1.0) -> None:
    """三次贝塞尔拆成多段直线，按 scale 缩放坐标"""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = ((u**3) * p1.x + 3 * (u**2) * t * p2.x + 3 * u * (t**2) * p3.x + (t**3) * p4.x) * scale
        y = ((u**3) * p1.y + 3 * (u**2) * t * p2.y + 3 * u * (t**2) * p3.y + (t**3) * p4.y) * scale
        pts.append((x, y))
    for j in range(len(pts) - 1):
        msp.add_line(pts[j], pts[j + 1], dxfattribs={"layer": "lines"})


def _bezier_to_lines_scaled(msp, p1, p2, p3, p4, steps: int = 8, scale: float = 1.0) -> None:
    """三次贝塞尔拆成多段直线，按 scale 缩放"""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = ((u**3) * p1.x + 3 * (u**2) * t * p2.x + 3 * u * (t**2) * p3.x + (t**3) * p4.x) * scale
        y = ((u**3) * p1.y + 3 * (u**2) * t * p2.y + 3 * u * (t**2) * p3.y + (t**3) * p4.y) * scale
        pts.append((x, y))
    for j in range(len(pts) - 1):
        msp.add_line(pts[j], pts[j + 1], dxfattribs={"layer": "lines"})