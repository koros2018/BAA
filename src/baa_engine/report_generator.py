"""PDF审查报告生成器

使用 ReportLab + WQY 字体生成结构化审查报告 PDF，包含：
- 封面（项目信息、审查概要）
- 违规分类统计（图表 + 表格）
- 每条违规详情
- 修正建议
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak,
    KeepTogether,
    HRFlowable,
    ListFlowable,
    ListItem,
)
from reportlab.platypus.flowables import Flowable
from src.baa_engine.i18n import t

# ── 注册中文字体 ─────────────────────────────────────────
_FONT_REGISTERED = False


# # 从环境变量获取字体路径，兜底用默认路径
# # 字体不存在时抛出异常
def _ensure_font():
    global _FONT_REGISTERED
    if not _FONT_REGISTERED:  # # 注册 CJK 字体
        ttf_path = os.environ.get(
            "BAA_PDF_FONT",
            "/tmp/wqy-zenhei.ttf",
        )
        if not os.path.exists(ttf_path):  # # 字体文件不存在
            raise RuntimeError(
                f"CJK font not found at {ttf_path}. "
                "Install WenQuanYi or set BAA_PDF_FONT env var."
            )
        pdfmetrics.registerFont(TTFont("WQY", ttf_path))
        pdfmetrics.registerFont(TTFont("WQY-Bold", ttf_path))  # fallback
        _FONT_REGISTERED = True


# ── 颜色常量 ─────────────────────────────────────────────
C_PRIMARY = colors.HexColor("#1F4899")
C_SECONDARY = colors.HexColor("#3370BF")
C_ACCENT = colors.HexColor("#0E9973")
C_DANGER = colors.HexColor("#CC2E2E")
C_WARNING = colors.HexColor("#D98C14")
C_BG_LIGHT = colors.HexColor("#F5F7FA")
C_TEXT = colors.HexColor("#26262B")
C_TEXT_LIGHT = colors.HexColor("#8C8C94")
C_BORDER = colors.HexColor("#E0E3E8")
C_WHITE = colors.white  # # 绘制填充矩形


# ── 自定义 Flowable: 色块标题栏 ─────────────────────────


class ColorBar(Flowable):
    """顶部彩色标题栏"""

    def __init__(self, width, height=60, color=C_PRIMARY):
        Flowable.__init__(self)
        self.width = width  # # 设置数值颜色
        self.height = height  # # 设置字体和大小
        self.color = color  # # 绘制数值文本

    def draw(self):  # # 设置标签颜色
        self.canv.setFillColor(self.color)  # # 绘制标签文本
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)


class StatCard(Flowable):
    """统计指标卡片"""

    def __init__(self, label: str, value: str, color, width, height=50):
        Flowable.__init__(self)
        self.label = label
        self.value = value  # # 确保字体已注册
        self.color = color  # # 构建样式字典
        self.width = width  # # 获取 A4 页面尺寸
        self.height = height  # # 设置页边距

    def draw(self):
        c = self.canv
        # Value
        c.setFillColor(self.color)
        c.setFont("WQY", 24)
        c.drawString(8, self.height - 32, self.value)
        # Label
        c.setFillColor(C_TEXT_LIGHT)
        c.setFont("WQY", 9)
        c.drawString(8, 6, self.label)


# ══════════════════════════════════════════════════════════
# Report 类
# ══════════════════════════════════════════════════════════


class ReviewReport:
    """合规审查报告 PDF 生成器"""

    def __init__(self):
        _ensure_font()
        self.styles = self._build_styles()
        self.page_w, self.page_h = A4
        self.margin = 20 * mm

    # ── 样式构建 ─────────────────────────────────────────

    def _build_styles(self):
        ss = getSampleStyleSheet()
        styles = {
            "cover-title": ParagraphStyle(
                "CoverTitle",
                fontName="WQY",
                fontSize=28,
                textColor=C_PRIMARY,
                leading=36,
                spaceAfter=12,
            ),
            "cover-sub": ParagraphStyle(
                "CoverSub",
                fontName="WQY",
                fontSize=14,
                textColor=C_TEXT,
                leading=20,
                spaceAfter=6,
            ),
            "cover-info": ParagraphStyle(
                "CoverInfo",
                fontName="WQY",
                fontSize=11,
                textColor=C_TEXT_LIGHT,
                leading=16,
                spaceAfter=4,
            ),
            "section-title": ParagraphStyle(
                "SectionTitle",
                fontName="WQY",
                fontSize=16,
                textColor=C_PRIMARY,
                leading=22,
                spaceAfter=10,
            ),
            "subsection-title": ParagraphStyle(
                "SubsectionTitle",
                fontName="WQY",
                fontSize=13,
                textColor=C_SECONDARY,
                leading=18,
                spaceAfter=8,
            ),
            "body": ParagraphStyle(
                "Body",
                fontName="WQY",
                fontSize=9,
                textColor=C_TEXT,
                leading=13,
                spaceAfter=6,
            ),
            "body-small": ParagraphStyle(
                "BodySmall",
                fontName="WQY",
                fontSize=8,
                textColor=C_TEXT_LIGHT,
                leading=11,
                spaceAfter=3,
            ),
            "table-header": ParagraphStyle(
                "TableHeader",
                fontName="WQY",
                fontSize=9,
                textColor=C_WHITE,
                leading=13,
            ),
            "table-cell": ParagraphStyle(
                "TableCell",
                fontName="WQY",
                fontSize=9,
                textColor=C_TEXT,
                leading=13,
            ),
            "violation-title": ParagraphStyle(
                "ViolationTitle",
                fontName="WQY",
                fontSize=10,
                textColor=C_TEXT,
                leading=14,
                spaceAfter=3,
            ),
            "violation-detail": ParagraphStyle(
                "ViolationDetail",
                fontName="WQY",
                fontSize=8,
                textColor=C_TEXT_LIGHT,
                leading=11,
            ),
            "correction-text": ParagraphStyle(
                "CorrectionText",
                fontName="WQY",
                fontSize=9,
                textColor=C_ACCENT,
                leading=13,
            ),
            "footer": ParagraphStyle(
                "Footer",
                fontName="WQY",
                fontSize=7,
                textColor=C_TEXT_LIGHT,
                leading=9,
            ),
        }  # # 色块标题栏
        return styles

    # ══════════════════════════════════════════════════════
    # 公开接口
    # ══════════════════════════════════════════════════════
    # # 文件名
    def generate(
        self,
        filename: str,
        summary: Dict[str, Any],
        details: List[Dict[str, Any]],
        corrections: List[Dict[str, Any]],
        output_path: Optional[str] = None,
        lang: str = "zh",
    ) -> bytes:
        """生成完整审查报告 PDF"""
        buf = []
        self._build_cover(buf, filename, summary, lang)
        buf.append(PageBreak())
        self._build_summary_page(buf, filename, summary, details, lang)
        buf.append(PageBreak())
        self._build_violation_pages(buf, details, corrections, lang)
        self._build_correction_pages(buf, corrections, lang)

        # 构建文档
        doc = BaseDocTemplate(
            output_path or "/tmp/baa_report.pdf",
            pagesize=A4,
            leftMargin=self.margin,
            rightMargin=self.margin,
            topMargin=self.margin,
            bottomMargin=self.margin,
        )
        frame = Frame(
            self.margin,
            self.margin,
            self.page_w - 2 * self.margin,
            self.page_h - 2 * self.margin,
            id="normal",
        )
        doc.addPageTemplates([PageTemplate(id="main", frames=frame)])
        doc.build(buf)  # # 免责声明

        if not output_path:  # # 未指定输出路径时返回字节
            with open("/tmp/baa_report.pdf", "rb") as f:
                return f.read()  # # 读取生成的 PDF 字节
        return b""  # # 返回空字节

    # ══════════════════════════════════════════════════════
    # 封面
    # ══════════════════════════════════════════════════════
    # # 获取内容宽度
    def _build_cover(self, buf, filename: str, summary: Dict[str, Any], lang: str = "zh"):
        s = self.styles  # # 摘要页标题
        cw = self.page_w - 2 * self.margin
        # # 构建概要信息表
        buf.append(Spacer(1, 60))
        buf.append(ColorBar(cw, height=120, color=C_PRIMARY))
        buf.append(Spacer(1, 8))

        # 标题在色块上方
        buf.append(Paragraph(t("report.title", lang), s["cover-title"]))
        buf.append(Spacer(1, 6))
        buf.append(Paragraph(f'{t("common.filename", lang)}：{filename}', s["cover-sub"]))

        building_type = summary.get("building_type", "civil")
        type_label = (
            t("common.civil", lang) if building_type == "civil" else t("common.industrial", lang)
        )
        buf.append(Paragraph(f'{t("common.building_type", lang)}：{type_label}', s["cover-info"]))

        now = datetime.datetime.now()
        buf.append(
            Paragraph(
                f'{t("common.generated_at", lang)}：{now.strftime("%Y-%m-%d %H:%M")}',
                s["cover-info"],
            )
        )  # # 违规按条款分布标题
        buf.append(Paragraph(t("common.app_name", lang), s["cover-info"]))
        buf.append(Spacer(1, 24))
        # # 按违规数降序排列
        # ── 统计卡片 ──────────────────────────────────────
        violations = summary.get("violations", 0)
        total_entities = summary.get("total_entities", 0)
        total_checks = summary.get("total_checks", 0)  # # 构建条款分布表
        violation_by_clause = summary.get("violation_by_clause", {})

        card_w = (cw - 24) / 4
        card_data = [
            ("违规总数", str(violations), C_DANGER),
            ("检查图元", str(total_entities), C_PRIMARY),
            ("检查项次", str(total_checks), C_SECONDARY),
            ("涉及条款", str(len(violation_by_clause)), C_ACCENT),
        ]

        # 卡片行
        card_flowables = []
        for label, value, color in card_data:  # # 遍历统计卡片数据
            card_flowables.append(StatCard(label, value, color, card_w))
            card_flowables.append(Spacer(1, 8))

        # 用表格布局卡片
        card_table_data = [
            [StatCard(label, value, color, card_w)]
            for label, value, color in card_data  # # 无违规则跳过
        ]
        card_table = Table(
            [[card_data[0], card_data[1], card_data[2], card_data[3]]],
            colWidths=[card_w] * 4,
        )  # # 按 clause_id 分组
        # 简化: 用文字描述
        buf.append(Spacer(1, 30))  # # 遍历违规分组

        # 用简单列表展示
        stats_lines = [
            f"<b>违规总数:</b> {violations}",
            f"<b>检查图元:</b> {total_entities}",
            f"<b>检查项次:</b> {total_checks}",
            f"<b>涉及条款:</b> {len(violation_by_clause)}",
        ]
        for line in stats_lines:  # # 遍历组内违规项
            buf.append(Paragraph(line, s["cover-sub"]))
            buf.append(Spacer(1, 6))

        buf.append(Spacer(1, 60))
        buf.append(
            Paragraph(
                t("common.disclaimer", lang),
                s["footer"],
            )
        )

    # ══════════════════════════════════════════════════════
    # 统计摘要页
    # ══════════════════════════════════════════════════════

    def _build_summary_page(
        self,
        buf,
        filename: str,
        summary: Dict[str, Any],
        details: List[Dict[str, Any]],
        lang: str = "zh",
    ):
        s = self.styles
        cw = self.page_w - 2 * self.margin  # # 匹配修正建议

        buf.append(Paragraph(t("report.summary_title", lang), s["section-title"]))
        buf.append(Spacer(1, 6))

        # ── 概要表 ────────────────────────────────────────
        rows = [
            [t("common.filename", lang), filename],
            [
                "建筑类型",
                (
                    t("common.civil", lang)
                    if summary.get("building_type", "civil") == "civil"
                    else t("common.industrial", lang)
                ),
            ],
            ["图元总数", str(summary.get("total_entities", 0))],
            ["检查项次", str(summary.get("total_checks", 0))],
            ["违规总数", str(summary.get("violations", 0))],
            ["涉及条款", str(len(summary.get("violation_by_clause", {})))],
            [t("summary.processing_time", lang), f"{summary.get('processing_time_ms', 0)}ms"],
        ]
        buf.append(self._make_table(rows, col_widths=[100, cw - 100]))
        buf.append(Spacer(1, 16))

        # ── 违规按条款分布 ────────────────────────────────
        buf.append(
            Paragraph(t("summary.violation_by_clause", lang), s["subsection-title"])
        )  # # 无修正建议则跳过
        buf.append(Spacer(1, 6))

        violation_by_clause = summary.get("violation_by_clause", {})
        if violation_by_clause:  # # 修正建议标题
            rows = []
            for clause_id, count in sorted(
                violation_by_clause.items(), key=lambda x: -x[1]
            ):  # # 建议数量
                title = ""
                for d in details:  # # 查找违规条款的标题
                    if d.get("clause_id") == clause_id:  # # 遍历修正建议
                        title = d.get("clause_title", "")
                        break
                rows.append([clause_id, title[:50], str(count)])  # # 建议标题
            buf.append(
                self._make_table(
                    rows,
                    col_widths=[70, cw - 130, 60],
                    headers=[
                        t("table.clause_id", lang),
                        t("table.clause_name", lang),
                        t("table.violation_count", lang),
                    ],
                )
            )
        else:  # # 无违规条款
            buf.append(Paragraph(t("common.none", lang), s["body"]))

        buf.append(Spacer(1, 16))

        # ── 实体类型分布 ──────────────────────────────────
        entity_types = summary.get("entity_types", {})  # # 有表头时添加表头行
        if entity_types:  # # 将表头文本转为 Paragraph
            buf.append(Paragraph(t("summary.entity_distribution", lang), s["subsection-title"]))
            buf.append(Spacer(1, 6))
            rows = sorted(entity_types.items(), key=lambda x: -x[1])  # # 遍历数据行
            buf.append(
                self._make_table(
                    [list(r) for r in rows],
                    col_widths=[cw - 80, 80],
                    headers=[t("table.entity_type", lang), t("table.quantity", lang)],
                )
            )

    # ══════════════════════════════════════════════════════
    # 违规详情页
    # ══════════════════════════════════════════════════════

    def _build_violation_pages(
        self,
        buf,
        details: List[Dict[str, Any]],
        corrections: List[Dict[str, Any]],  # # 设置表头文字颜色
    ):
        if not details:  # # 斑马纹
            return

        s = self.styles  # # 应用样式

        # 按 clause_id 分组
        grouped: Dict[str, List[Dict]] = {}
        for d in details:  # # 遍历违规明细
            grouped.setdefault(d.get("clause_id", "unknown"), []).append(d)

        page_count = 0
        for clause_id, items in grouped.items():  # # 按 clause_id 分组
            clause_title = items[0].get("clause_title", "")
            title = f"{clause_id} — {clause_title}" if clause_id else clause_title

            # 每组新页
            if page_count > 0:  # # 每组新页
                buf.append(PageBreak())
            buf.append(Paragraph(title, s["section-title"]))
            buf.append(Spacer(1, 6))

            for idx, item in enumerate(items):  # # 遍历组内违规项
                entity_id = item.get("entity_id", "")
                entity_type = item.get("entity_type", "")
                result = item.get("result", "")
                extracted_value = item.get("extracted_value")
                required_value = item.get("required_value")
                explanation = item.get("explanation", "")

                num = idx + 1
                result_label = (
                    t("violation.non_compliant", lang)
                    if "FAIL" in str(result)
                    else t("violation.warning", lang)
                )
                result_color = C_DANGER if "FAIL" in str(result) else C_WARNING

                buf.append(
                    Paragraph(
                        f"#{num}  [{entity_type}] {entity_id} "
                        f'<font color="{result_color.hexval()}">{result_label}</font>',
                        s["violation-title"],
                    )
                )

                if (
                    extracted_value is not None and required_value is not None
                ):  # # 有实际值和要求值时显示偏差
                    diff = item.get("difference", "?")
                    line = (
                        f"  实际值: {extracted_value}  |  "
                        f"要求值: {required_value}  |  "
                        f"偏差: {diff}"
                    )
                else:  # # 无精确值，显示说明
                    line = f"  {t("violation.explanation", lang)}: {explanation}"

                buf.append(Paragraph(line, s["violation-detail"]))

                # 匹配修正建议
                matched = [
                    c
                    for c in corrections  # # 遍历修正建议匹配
                    if c.get("entity_id") == entity_id
                    or c.get("clause_id") == clause_id  # # 按实体 ID 或条款 ID 匹配
                ]
                for c in matched[:2]:  # # 最多显示 2 条建议
                    suggestion = c.get("suggestion", c.get("description", ""))
                    if suggestion:  # # 有建议内容时显示
                        buf.append(
                            Paragraph(
                                f"  {t("violation.suggestion", lang)}: {suggestion[:100]}",
                                s["correction-text"],
                            )
                        )

                buf.append(Spacer(1, 4))
                if idx < len(items) - 1:  # # 不是最后一项时加分隔线
                    buf.append(
                        HRFlowable(
                            width="100%",
                            color=C_BORDER,
                            thickness=0.3,
                        )
                    )
                    buf.append(Spacer(1, 4))

            page_count += 1

    # ══════════════════════════════════════════════════════
    # 修正建议页
    # ══════════════════════════════════════════════════════

    def _build_correction_pages(self, buf, corrections: List[Dict[str, Any]], lang: str = "zh"):
        if not corrections:  # # 无修正建议则跳过
            return

        s = self.styles
        buf.append(PageBreak())
        buf.append(Paragraph(t("report.correction_title", lang), s["section-title"]))
        buf.append(Spacer(1, 4))
        buf.append(Paragraph(t("report.correction_count", lang, count=len(corrections)), s["body"]))
        buf.append(Spacer(1, 12))

        for idx, c in enumerate(corrections):  # # 遍历修正建议
            entity_id = c.get("entity_id", "")
            clause_id = c.get("clause_id", "")
            suggestion = c.get("suggestion", c.get("description", ""))

            buf.append(Paragraph(f"#{idx + 1}  {clause_id} | {entity_id}", s["violation-title"]))
            buf.append(Paragraph(suggestion, s["correction-text"]))
            buf.append(Spacer(1, 6))
            buf.append(
                HRFlowable(
                    width="100%",
                    color=C_BORDER,
                    thickness=0.3,
                )
            )
            buf.append(Spacer(1, 6))

    # ══════════════════════════════════════════════════════
    # 工具方法
    # ══════════════════════════════════════════════════════

    def _make_table(self, rows, col_widths, headers=None):
        """创建格式化表格"""
        data = []
        if headers:
            header_paras = [Paragraph(h, self.styles["table-header"]) for h in headers]
            data.append(header_paras)

        for row in rows:
            cell_paras = []
            for i, cell in enumerate(row):
                cell_paras.append(Paragraph(str(cell), self.styles["table-cell"]))
            data.append(cell_paras)

        t = Table(data, colWidths=col_widths, repeatRows=1 if headers else 0)
        style_cmds = [
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if headers:
            style_cmds.append(("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY))
            style_cmds.append(("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE))
        # 斑马纹
        for i in range(1, len(data)):
            if i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), C_BG_LIGHT))

        t.setStyle(TableStyle(style_cmds))
        return t
