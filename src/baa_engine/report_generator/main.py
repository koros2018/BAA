"""
BAA 审查报告 PDF 生成器（重构版）

拆分结构（P85）：
  report_generator/
    components.py    — 颜色/字体/Flowable/样式/表格工具
    main.py          — ReviewReport 薄层编排
    cover.py         — 封面页
    score.py         — 合规度评分页
    diff.py          — 版本对比页
    summary.py       — 统计摘要页 + 结构化摘要页
    violations.py    — 违规详情页 + 修正建议页
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from .components import (
    ensure_font,
    build_styles,
    build_doc,
    PageBreak,
)
from .cover import build_cover
from .score import build_score_page
from .diff import build_diff_page
from .summary import build_summary_page, build_structured_summary_page
from .violations import build_violation_pages, build_correction_pages


class ReviewReport:
    """合规审查报告 PDF 生成器（薄层编排器）"""

    def __init__(self) -> None:
        """初始化实例。"""
        ensure_font()
        self.styles = build_styles()
        self.page_w, self.page_h = A4
        self.margin = 20 * mm

    def generate(
        self,
        filename: str,
        summary: Dict[str, Any],
        details: List[Dict[str, Any]],
        corrections: List[Dict[str, Any]],
        output_path: Optional[str] = None,
        lang: str = "zh",
        diff_report: Optional[Dict[str, Any]] = None,
        structured_summary: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """生成完整审查报告 PDF"""
        buf: List[Any] = []

        build_cover(buf, self.styles, self.page_w, self.margin, filename, summary, lang)
        buf.append(PageBreak())

        build_score_page(buf, self.styles, self.page_w, self.margin, summary, lang, details)
        buf.append(PageBreak())

        build_summary_page(
            buf, self.styles, self.page_w, self.margin, filename, summary, details, lang
        )
        buf.append(PageBreak())

        if structured_summary:
            build_structured_summary_page(
                buf, self.styles, self.page_w, self.margin, structured_summary, lang
            )
            buf.append(PageBreak())

        if diff_report:
            build_diff_page(buf, self.styles, self.page_w, self.margin, diff_report, lang)
            buf.append(PageBreak())

        build_violation_pages(buf, self.styles, details, corrections, lang)
        build_correction_pages(buf, self.styles, corrections, lang)

        return build_doc(self.page_w, self.page_h, self.margin, output_path, buf)
