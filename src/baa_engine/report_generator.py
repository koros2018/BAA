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
from reportlab.lib.units import mm
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
    HRFlowable,
)
from reportlab.platypus.flowables import Flowable
from src.baa_engine.i18n import t

# ── 注册中文字体 ─────────────────────────────────────────
_FONT_REGISTERED = False  # _FONT_REGISTERED: False


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
        _FONT_REGISTERED = True  # _FONT_REGISTERED: True


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
        self.canv.rect(
            0, 0, self.width, self.height, fill=1, stroke=0
        )  # self.canv.rect(0, 0, self.width, self.height, fill: 1, stroke=0)


class StatCard(Flowable):
    """统计指标卡片"""

    def __init__(self, label: str, value: str, color, width, height=50):
        Flowable.__init__(self)
        self.label = label  # self.label: label
        self.value = value  # # 确保字体已注册
        self.color = color  # # 构建样式字典
        self.width = width  # # 获取 A4 页面尺寸
        self.height = height  # # 设置页边距

    def draw(self):
        c = self.canv
        # canvas: PDF 绘图上下文
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
        self.styles = self._build_styles()  # self.styles: self._build_styles()
        self.page_w, self.page_h = A4  # self.page_w, self.page_h: A4
        self.margin = 20 * mm  # self.margin: 20 * mm

    # margin: 页边距

    # ── 样式构建 ─────────────────────────────────────────

    def _build_styles(self):
        ss = getSampleStyleSheet()  # ss: getSampleStyleSheet()
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

    # return:

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
        diff_report: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """生成完整审查报告 PDF"""
        buf = []  # buf: []
        self._build_cover(buf, filename, summary, lang)
        # build: 调用子模块方法
        buf.append(PageBreak())  # buf: buf.append(PageBreak())
        self._build_score_page(buf, summary, lang)
        # build: 调用子模块方法
        buf.append(PageBreak())  # buf: buf.append(PageBreak())
        self._build_summary_page(buf, filename, summary, details, lang)
        # build: 调用子模块方法
        buf.append(PageBreak())  # buf: buf.append(PageBreak())
        if diff_report:  # diff_report: P42 版本对比
            self._build_diff_page(buf, diff_report, lang)
            # build: 调用子模块方法
            buf.append(PageBreak())  # buf: buf.append(PageBreak())
        self._build_violation_pages(buf, details, corrections, lang)
        # build: 调用子模块方法
        self._build_correction_pages(buf, corrections, lang)
        # build: 调用子模块方法

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
            # margin: 页边距
            self.margin,
            # margin: 页边距
            self.page_w - 2 * self.margin,
            self.page_h - 2 * self.margin,
            id="normal",
        )
        doc.addPageTemplates(
            [PageTemplate(id="main", frames=frame)]
        )  # doc.addPageTemplates([PageTemplate(id: "main", frames=frame)])
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
        cw = self.page_w - 2 * self.margin  # cw: self.page_w - 2 * self.margin
        # cw: 内容宽度
        # # 构建概要信息表
        buf.append(Spacer(1, 60))  # buf: buf.append(Spacer(1, 60))
        buf.append(
            ColorBar(cw, height=120, color=C_PRIMARY)
        )  # buf: buf.append(ColorBar(cw, height=120, color=C_PRIMARY))
        buf.append(Spacer(1, 8))  # buf: buf.append(Spacer(1, 8))

        # 标题在色块上方
        buf.append(
            Paragraph(t("report.title", lang), s["cover-title"])
        )  # buf: buf.append(Paragraph(t('report.title', lang), s['cover-title']))
        buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))
        buf.append(Paragraph(f'{t("common.filename", lang)}：{filename}', s["cover-sub"]))
        # paragraph: 文本段落

        building_type = summary.get(
            "building_type", "civil"
        )  # building_type: summary.get("building_type", "civil")
        # building_type: 建筑类型
        type_label = (
            # type_label: 类型翻译
            t("common.civil", lang)
            if building_type == "civil"
            else t(
                "common.industrial", lang
            )  # t("common.civil", lang) if building_type: = "civil" else t("common.industrial", la
        )
        buf.append(Paragraph(f'{t("common.building_type", lang)}：{type_label}', s["cover-info"]))
        # paragraph: 文本段落

        now = datetime.datetime.now()  # now: datetime.datetime.now()
        # now: 生成时间
        buf.append(  # buf: buf.append(
            Paragraph(
                f'{t("common.generated_at", lang)}：{now.strftime("%Y-%m-%d %H:%M")}',
                s["cover-info"],
            )
        )  # # 违规按条款分布标题
        buf.append(
            Paragraph(t("common.app_name", lang), s["cover-info"])
        )  # buf: buf.append(Paragraph(t('common.app_name', lang), s['cover-info']))
        buf.append(Spacer(1, 24))  # buf: buf.append(Spacer(1, 24))
        # # 按违规数降序排列
        # ── 统计卡片 ──────────────────────────────────────
        violations = summary.get("violations", 0)  # violations: summary.get("violations", 0)
        total_entities = summary.get(
            "total_entities", 0
        )  # total_entities: summary.get("total_entities", 0)
        total_checks = summary.get("total_checks", 0)  # # 构建条款分布表
        violation_by_clause = summary.get(
            "violation_by_clause", {}
        )  # violation_by_clause: summary.get("violation_by_clause", {})

        card_w = (cw - 24) / 4  # card_w: 卡片宽度计算
        card_data = [  # card_data: 4 个统计卡片数据
            ("违规总数", str(violations), C_DANGER),
            ("检查图元", str(total_entities), C_PRIMARY),
            ("检查项次", str(total_checks), C_SECONDARY),
            ("涉及条款", str(len(violation_by_clause)), C_ACCENT),
            # 封面统计卡片：展示 4 个核心指标
            # card_data 是 4 元组列表：(标签, 数值, 颜色)
            # card_w 由封面内容宽度等分 4 列计算
        ]

        # 卡片行
        card_flowables = []  # card_flowables: []
        # card_flowables: 流式布局列表
        # card_flowables 是临时流式列表，后续被 card_table 替代
        # StatCard 用 Flowable 自定义绘制，比 ReportLab 内建样式更灵活
        for label, value, color in card_data:  # # 遍历统计卡片数据
            card_flowables.append(StatCard(label, value, color, card_w))
            # card_flowables: 追加 Flowable
            card_flowables.append(Spacer(1, 8))
        # card_flowables: 追加 Flowable

        # 用表格布局卡片
        # card_table 用真实数据 card_data[0..3] 构建 1 行 4 列表格
        # 表格比流式布局更稳定，不会因为 Flowable 高度不一致导致错位
        card_table_data = [  # card_table_data: 表格布局卡片数据
            [StatCard(label, value, color, card_w)]
            for label, value, color in card_data  # # 无违规则跳过
        ]
        card_table = Table(
            [[card_data[0], card_data[1], card_data[2], card_data[3]]],
            colWidths=[card_w] * 4,
        )  # # 按 clause_id 分组
        # 用 Paragraph 列表替代 StatCard：简单列表布局在 PDF 中更可靠
        # ReportLab Flowable 的 StatCard 卡片在不同版本行为不稳定
        # 简化: 用文字描述
        buf.append(Spacer(1, 30))  # # 遍历违规分组

        # 用简单列表展示
        stats_lines = [
            # stats_lines: 简单统计文本
            f"<b>违规总数:</b> {violations}",
            f"<b>检查图元:</b> {total_entities}",
            f"<b>检查项次:</b> {total_checks}",
            f"<b>涉及条款:</b> {len(violation_by_clause)}",
        ]
        for line in stats_lines:  # # 遍历组内违规项
            buf.append(
                Paragraph(line, s["cover-sub"])
            )  # buf: buf.append(Paragraph(line, s['cover-sub']))
            buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))

        buf.append(Spacer(1, 60))  # buf: buf.append(Spacer(1, 60))
        buf.append(  # buf: buf.append(
            Paragraph(
                t("common.disclaimer", lang),
                s["footer"],
            )
        )

    # ══════════════════════════════════════════════════════
    # 合规度评分页
    # ══════════════════════════════════════════════════════

    def _build_score_page(
        self,
        buf,
        summary: Dict[str, Any],
        lang: str = "zh",
    ):
        """合规度评分页：总体评分 + 合规率 + 严重级别分布

        总体评分来自 summary.overall_score，评分来源有二：
        直接传的 overall_score，或 fallback 到 summary.get("score")
        兼容旧 API 返回格式（score 字段已被 overall_score 替代但未废弃）。
        合规率来自 summary.compliance_rate（合规实体 / 检查实体）。
        严重级别分布来自 summary.severity_distribution。
        这三个指标是用户最关心的概览数据，放在评分页优先展示。
        """
        s = self.styles
        # styles: 样式字典
        cw = self.page_w - 2 * self.margin  # cw: self.page_w - 2 * self.margin
        # cw: 内容宽度

        # 标题
        buf.append(
            Paragraph(t("report.summary_title", lang), s["section-title"])
        )  # buf: buf.append(Paragraph(t('report.summary_title', lang), s['section-title
        buf.append(Spacer(1, 8))  # buf: buf.append(Spacer(1, 8))

        # 总体评分
        overall_score = summary.get(
            "overall_score", summary.get("score")
        )  # overall_score: summary.get("overall_score", summary.get
        if overall_score is not None:  # overall_score: 总体评分
            card_w = (cw - 16) / 2  # card_w: 卡片宽度计算
            # 评分四档分级（《消防设施通用规范》GB 55036 参考）
            # 90+ 优秀（基本无隐患）
            # 70-89 良好（少量整改项）
            # 50-69 一般（较多问题，需专项整改）
            # <50 不合格（存在重大隐患，限期整改）
            # 评分四档分级（《消防设施通用规范》GB 55036 参考）
            # 90+ 优秀（基本无隐患）
            # 70-89 良好（少量整改项）
            # 50-69 一般（较多问题，需专项整改）
            # <50 不合格（存在重大隐患，限期整改）
            # 使用 elif 链确保评分只命中最高一档，避免重复着色
            if overall_score >= 90:
                # overall_score 存在
                score_color, score_label = (
                    C_ACCENT,
                    "优秀",
                )  # score_color, score_label: C_ACCENT, "优秀"
            elif overall_score >= 70:
                score_color, score_label = (
                    C_PRIMARY,
                    "良好",
                )  # score_color, score_label: C_PRIMARY, "良好"
            # 总体评分四档分级：90+ 优秀，70+ 良好，50+ 一般，<50 不合格
            # score_color 用于 StatCard 的配色，score_label 用于中文标签显示
            elif overall_score >= 50:
                score_color, score_label = (
                    C_WARNING,
                    "一般",
                )  # score_color, score_label: C_WARNING, "一般"
            else:
                score_color, score_label = (
                    C_DANGER,
                    "不合格",
                )  # score_color, score_label: C_DANGER, "不合格"
            buf.append(  # buf: buf.append(
                StatCard(t("cover.score", lang), f"{int(overall_score)}", score_color, card_w, 70)
            )
            buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))
            buf.append(
                Paragraph(f"等级：{score_label} ({overall_score:.1f}/100)", s["body"])
            )  # buf: buf.append(Paragraph(f'等级：{score_label} ({overall_score:.1f}/100)', s[
            buf.append(Spacer(1, 12))  # buf: buf.append(Spacer(1, 12))

        # 合规率：summary 可能传 float(0.85) 或 int(85)
        # 统一转为整数百分比展示，避免 UI 上同时出现 0.85 和 85% 的歧义
        compliance_rate = summary.get(
            "compliance_rate", 0.0
        )  # compliance_rate: summary.get("compliance_rate", 0.0)
        if isinstance(compliance_rate, float):
            compliance_pct = int(
                compliance_rate * 100
            )  # compliance_pct: int(compliance_rate * 100)
        # 合规率计算：float 型(0.85) 转为 int 百分比(85)，int 型(85) 直接使用
        # 避免 UI 上同时出现 0.85 和 85% 的歧义显示
        else:
            compliance_pct = compliance_rate  # compliance_pct: compliance_rate
        if compliance_pct != 0:
            # compliance_pct 非零
            card_w = (cw - 16) / 2  # card_w: 卡片宽度计算
            cr_color = (
                C_ACCENT
                if compliance_pct >= 80
                # compliance_pct 非零
                else (C_WARNING if compliance_pct >= 50 else C_DANGER)
            )
            buf.append(  # buf: buf.append(
                StatCard(
                    t("cover.compliance_rate", lang),
                    f"{compliance_pct}%",
                    cr_color,
                    card_w,
                    70,
                    # 严重级别分布：summary.severity_distribution 来自审查引擎
                    # severity_dist 是 Dict[str, int]，key 是 severity 级别，value 是数量
                    # sev_map 用于将英文 severity 关键字映射为中文显示
                )
            )
            buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))
            buf.append(
                Paragraph(f"通过率：{compliance_pct}%", s["body"])
            )  # buf: buf.append(Paragraph(f'通过率：{compliance_pct}%', s['body']))
            buf.append(Spacer(1, 16))  # buf: buf.append(Spacer(1, 16))

        # 严重级别分布
        severity_dist = summary.get(
            "severity_distribution", {}
        )  # severity_dist: summary.get("severity_distribution", {})
        if severity_dist:  # severity_dist: 严重级别分布
            buf.append(  # buf: buf.append(
                Paragraph(
                    t("stat.violations", lang) + " - " + t("common.by_type", lang),
                    # 实体类型分布：summary.entity_types 来自审查引擎统计
                    # 按数量降序排列，帮助快速发现图纸中哪类实体数量最多
                    s["subsection-title"],
                )
            )
            buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))
            sev_map = {
                "critical": "严重",
                "major": "较大",
                "minor": "一般",
            }  # sev_map: {"critical": "严重", "major": "较大", "minor
            # sev_map: severity 中英文映射
            rows = [
                [sev_map.get(k, k), str(v)] for k, v in sorted(severity_dist.items())
            ]  # rows: 表格数据行列表
            buf.append(  # buf: buf.append(
                self._make_table(
                    rows, col_widths=[cw - 80, 80], headers=["严重级别", "数量"]
                )  # self._make_table(rows, col_widths: [cw - 80, 80], headers=["严重级别", "数量"])
                # make_table: 格式化表格
            )
            buf.append(Spacer(1, 16))  # buf: buf.append(Spacer(1, 16))

        # 平均置信度（P36 新增）：展示项目整体置信度均值
        # avg_confidence 来自 summary.avg_confidence，范围 0.0 ~ 1.0
        # 置信度分级：0.85+ 优秀(绿)，0.6+ 一般(橙)，<0.6 不合格(红)
        # 实体类型分布
        entity_types = summary.get(
            "entity_types", {}
        )  # entity_types: summary.get("entity_types", {})
        if entity_types:  # entity_types: 实体类型分布统计
            buf.append(Paragraph(t("summary.entity_distribution", lang), s["subsection-title"]))
            # paragraph: 多语言文本
            buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))
            rows = sorted(
                entity_types.items(), key=lambda x: -x[1]
            )  # rows: sorted(entity_types.items(), key=lambda
            buf.append(  # buf: buf.append(
                self._make_table(
                    # make_table: 格式化表格
                    [list(r) for r in rows],
                    col_widths=[cw - 80, 80],
                    headers=[
                        t("table.entity_type", lang),
                        t("table.quantity", lang),
                    ],  # headers: [t("table.entity_type", lang), t("table.
                )
            )

        # 平均置信度（P36）
        avg_confidence = summary.get(
            "avg_confidence"
        )  # avg_confidence: summary.get("avg_confidence")
        if avg_confidence is not None and avg_confidence > 0:  # avg_confidence: P36 置信度指标
            buf.append(Spacer(1, 12))  # buf: buf.append(Spacer(1, 12))
            card_w = (cw - 16) / 2  # card_w: 卡片宽度计算
            conf_color = (
                C_ACCENT
                if avg_confidence >= 0.85
                # avg_confidence 存在
                else (C_WARNING if avg_confidence >= 0.6 else C_DANGER)
            )
            buf.append(  # buf: buf.append(
                StatCard(
                    # 版本对比页（P42 新增）：展示 v1 vs v2 的变更概览
                    # diff_report 包含 summary(变更统计) 和 items(变更明细) 两层数据
                    t("report.avg_confidence", lang),
                    f"{int(avg_confidence * 100)}%",
                    conf_color,
                    card_w,
                    70,
                )
            )

        # ══════════════════════════════════════════════════════
        # 变更摘要卡片：新增/已修复/已变更三类违规数量
        # new_violations：v2 新增但 v1 不存在的违规（红色）
        # fixed_violations：v1 存在但 v2 已修复的违规（绿色）
        # changed_violations：两侧都存在但内容变化的违规（蓝色）
        # 版本对比页
        # ══════════════════════════════════════════════════════

    def _build_diff_page(
        self,
        buf,
        diff_report: Dict[str, Any],
        lang: str = "zh",
    ):
        """版本对比报告页：展示 v1 vs v2 的变更概览和详情"""  # # 文件名
        s = self.styles
        # styles: 样式字典
        cw = self.page_w - 2 * self.margin  # cw: self.page_w - 2 * self.margin
        # cw: 内容宽度

        # 标题
        v1_file = diff_report.get("v1_file", "")  # v1_file: diff_report.get("v1_file", "")
        # 变更明细表：逐条展示每个变更的类型、条款 ID、实体 ID
        # diff_type 映射：new -> 新增，fixed -> 已修复，changed -> 已变更
        v2_file = diff_report.get("v2_file", "")  # v2_file: diff_report.get("v2_file", "")
        title_text = t("report.diff_title", lang, v1=v1_file, v2=v2_file)
        buf.append(
            Paragraph(title_text, s["section-title"])
        )  # buf: buf.append(Paragraph(title_text, s['section-title']))
        buf.append(Spacer(1, 8))  # buf: buf.append(Spacer(1, 8))

        # 变更摘要
        summary = diff_report.get("summary", {})  # summary: diff_report.get("summary", {})
        new_violations = summary.get(
            "new_violations", 0
        )  # new_violations: summary.get("new_violations", 0)
        fixed_violations = summary.get(
            "fixed_violations", 0
        )  # fixed_violations: summary.get("fixed_violations", 0)
        changed_violations = summary.get(
            "changed_violations", 0
        )  # changed_violations: summary.get("changed_violations", 0)
        total_v1 = summary.get("total_v1", 0)  # total_v1: summary.get("total_v1", 0)
        total_v2 = summary.get("total_v2", 0)  # total_v2: summary.get("total_v2", 0)

        # 摘要卡片
        card_w = (cw - 24) / 3  # card_w: 卡片宽度计算
        buf.append(StatCard(t("report.diff_new", lang), str(new_violations), C_DANGER, card_w, 50))
        # statcard: 统计卡片
        buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))
        buf.append(  # buf: buf.append(
            StatCard(t("report.diff_fixed", lang), str(fixed_violations), C_ACCENT, card_w, 50)
        )
        buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))
        buf.append(  # buf: buf.append(
            StatCard(
                t("report.diff_changed", lang), str(changed_violations), C_SECONDARY, card_w, 50
            )
        )
        buf.append(Spacer(1, 16))  # buf: buf.append(Spacer(1, 16))

        # 变更明细表
        items = diff_report.get("items", [])  # items: diff_report.get("items", [])
        if items:
            buf.append(
                Paragraph(t("report.diff_details", lang), s["subsection-title"])
            )  # buf: buf.append(Paragraph(t('report.diff_details', lang), s['subsection-tit
            buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))
            rows = []  # rows: 表格数据行列表
            for item in items:  # items: 版本对比明细列表
                diff_type = item.get("diff_type", "")  # diff_type: item.get("diff_type", "")
                type_map = {
                    "new": t("report.diff_new", lang),
                    "fixed": t("report.diff_fixed", lang),
                    "changed": t("report.diff_changed", lang),
                }
                type_label = type_map.get(
                    diff_type, diff_type
                )  # type_label: type_map.get(diff_type, diff_type)
                clause_id = item.get("clause_id", "")  # clause_id: item.get("clause_id", "")
                # 统计摘要页：概要表 + 违规按条款分布 + 实体类型分布
                # 三块信息互补：条款分布帮助定位规范缺口，实体分布帮助定位图纸问题区域
                entity = item.get("entity_id", "")  # entity: item.get("entity_id", "")
                rows.append([type_label, clause_id, entity])
            buf.append(  # buf: buf.append(
                self._make_table(
                    # make_table: 格式化表格
                    rows,
                    col_widths=[
                        (cw - 200) / 2,
                        cw - 200,
                        (cw - 200) / 2,
                    ],  # col_widths: [(cw - 200) / 2, cw - 200, (cw - 200) /
                    headers=[
                        t("report.diff_type", lang),
                        t("table.clause_id", lang),
                        t("table.entity_type", lang),
                    ],
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
        """统计摘要页：概要表 + 违规按条款分布 + 实体类型分布

        概要表展示项目级基本信息，违规按条款分布展示哪些规范条款被触发的最多
        （降序排列，最严重问题排前面）。实体类型分布展示哪些实体类型数量最多。
        三块信息互补：条款分布帮助定位规范缺口，实体分布帮助定位图纸问题区域。
        """
        # 违规按条款分布：按 violation count 降序排列
        # 标题从 details 中查找，因为 summary 只存 count，不存 clause_title
        # title[:50] 截断防止表格过宽
        s = self.styles
        # styles: 样式字典
        cw = self.page_w - 2 * self.margin  # # 匹配修正建议

        buf.append(
            Paragraph(t("report.summary_title", lang), s["section-title"])
        )  # buf: buf.append(Paragraph(t('report.summary_title', lang), s['section-title
        buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))

        # ── 概要表 ────────────────────────────────────────
        # 概要表包含 7 项基本信息，其中建筑类型通过 i18n 翻译展示中文/英文
        # processing_time_ms 用于帮助判断审查耗时是否正常（>60000ms 可能存问题）
        rows = [  # rows: 表格数据行列表
            [t("common.filename", lang), filename],
            [
                "建筑类型",
                (
                    t("common.civil", lang)
                    # 条款分布表的列宽分配：条款 ID 70，条款名称 cw-130，违规数量 60
                    # 列宽之和应等于内容宽度 cw，三个宽度相加需等于 cw
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
        buf.append(
            self._make_table(rows, col_widths=[100, cw - 100])
        )  # buf: buf.append(self._make_table(rows, col_widths=[100, cw - 100]))
        buf.append(Spacer(1, 16))  # buf: buf.append(Spacer(1, 16))

        # ── 违规按条款分布 ────────────────────────────────
        # 按 violation count 降序排列，数量最多的条款说明图纸在该规范方向问题最多
        # 实体类型分布表：按数量降序，列宽 80/80 对称分配
        # entity_types 来自审查引擎的 entity_counter 统计
        # clause_title 从 details 中查找：同一个 clause_id 对应同一个条款标题，
        # 标题取第 50 字符防止表格过宽
        buf.append(  # buf: buf.append(
            Paragraph(t("summary.violation_by_clause", lang), s["subsection-title"])
        )  # # 无修正建议则跳过
        buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))

        violation_by_clause = summary.get(
            "violation_by_clause", {}
        )  # violation_by_clause: summary.get("violation_by_clause", {})
        if violation_by_clause:  # # 修正建议标题
            rows = []  # rows: 表格数据行列表
            for clause_id, count in sorted(
                violation_by_clause.items(),
                key=lambda x: -x[1],  # violation_by_clause.items(), key: lambda x: -x[1]
            ):  # # 建议数量
                title = ""  # title: ""
                for d in details:  # # 查找违规条款的标题
                    if d.get("clause_id") == clause_id:  # # 遍历修正建议
                        title = d.get("clause_title", "")  # title: d.get("clause_title", "")
                        break
                rows.append([clause_id, title[:50], str(count)])  # # 建议标题
            buf.append(  # buf: buf.append(
                self._make_table(
                    # make_table: 格式化表格
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
            buf.append(
                Paragraph(t("common.none", lang), s["body"])
            )  # buf: buf.append(Paragraph(t('common.none', lang), s['body']))

        buf.append(Spacer(1, 16))  # buf: buf.append(Spacer(1, 16))

        # ── 实体类型分布 ──────────────────────────────────
        # 实体类型数量按降序排列，帮助发现图纸中哪类实体最多
        # 数量异常的类型（如大量 door 但数量不匹配 room）可能是图纸或解析问题
        entity_types = summary.get("entity_types", {})  # # 有表头时添加表头行
        if entity_types:  # # 将表头文本转为 Paragraph
            buf.append(Paragraph(t("summary.entity_distribution", lang), s["subsection-title"]))
            # paragraph: 多语言文本
            # 违规详情页：按 clause_id 分组，同一条款的违规放在一起便于批量处理
            # 每条违规展示：实体信息、合规结果、偏差值、置信度、匹配修正建议
            # 每组占一页，避免单页内容过多导致可读性差
            buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))
            rows = sorted(entity_types.items(), key=lambda x: -x[1])  # # 遍历数据行
            buf.append(  # buf: buf.append(
                self._make_table(
                    # make_table: 格式化表格
                    [list(r) for r in rows],
                    col_widths=[cw - 80, 80],
                    headers=[
                        t("table.entity_type", lang),
                        t("table.quantity", lang),
                    ],  # headers: [t("table.entity_type", lang), t("table.
                )
            )

    # ══════════════════════════════════════════════════════
    # 违规详情页
    # ══════════════════════════════════════════════════════

    def _build_violation_pages(
        self,
        buf,
        details: List[Dict[str, Any]],
        corrections: List[Dict[str, Any]],
        lang: str = "zh",  # 语言
    ):
        if not details:  # # 斑马纹
            return
        # 结果标签：FAIL -> 不合规(红色)，WARNING -> 警告(橙色)
        # result 字段来自原子函数返回的 FuncResult，可能包含 FAIL/WARN/DEGRADED

        s = self.styles  # # 应用样式

        # 按 clause_id 分组
        grouped: Dict[str, List[Dict]] = {}  # grouped: Dict[str, List[Dict]]: {}
        for d in details:  # # 遍历违规明细
            grouped.setdefault(d.get("clause_id", "unknown"), []).append(d)

        # 偏差显示：有精确值时展示 "实际值 | 要求值 | 偏差"
        # 偏差 = 实际值 - 要求值，正值表示超出，负值表示不足
        # 无精确值时展示解释文本（如 "防火门等级不足"）
        page_count = 0  # page_count: 0
        # page_count: 初始化
        for clause_id, items in grouped.items():  # # 按 clause_id 分组
            clause_title = items[0].get(
                "clause_title", ""
            )  # clause_title: items[0].get("clause_title", "")
            title = (
                f"{clause_id} — {clause_title}" if clause_id else clause_title
            )  # title: f"{clause_id} — {clause_title}" if claus

            # 每组新页
            # 第一组不加分隔页，从第二组开始每组前加 PageBreak
            if page_count > 0:  # # 每组新页
                buf.append(PageBreak())  # buf: buf.append(PageBreak())
            buf.append(
                Paragraph(title, s["section-title"])
            )  # buf: buf.append(Paragraph(title, s['section-title']))
            buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))

            # 置信度显示（P36 新增）：item.get("confidence") 来自审查引擎
            # 置信度用于展示该违规判定的置信程度，帮助用户判断是否需要人工复核
            for idx, item in enumerate(items):  # # 遍历组内违规项
                entity_id = item.get("entity_id", "")  # entity_id: item.get("entity_id", "")
                entity_type = item.get(
                    "entity_type", ""
                )  # entity_type: item.get("entity_type", "")
                result = item.get("result", "")  # result: item.get("result", "")
                extracted_value = item.get(
                    "extracted_value"
                )  # extracted_value: item.get("extracted_value")
                required_value = item.get(
                    "required_value"
                )  # required_value: item.get("required_value")
                # 匹配修正建议：按 entity_id 精确匹配优先，clause_id 模糊匹配兜底
                # 同一违规可能有多条建议，最多展示 2 条避免页面过长
                # matched 列表通过 entity_id 或 clause_id 与修正建议关联
                explanation = item.get(
                    "explanation", ""
                )  # explanation: item.get("explanation", "")

                num = idx + 1  # num: idx + 1
                result_label = (
                    # result_label: 结果标签
                    t("violation.non_compliant", lang)
                    if "FAIL" in str(result)
                    else t("violation.warning", lang)
                )
                result_color = (
                    C_DANGER if "FAIL" in str(result) else C_WARNING
                )  # result_color: C_DANGER if "FAIL" in str(result) else C
                # result_color: 结果颜色

                buf.append(  # buf: buf.append(
                    Paragraph(
                        f"#{num}  [{entity_type}] {entity_id} "
                        f'<font color="{result_color.hexval()}">{result_label}</font>',  # f'<font color: "{result_color.hexval()}">{result_label}
                        s["violation-title"],
                    )
                )

                if extracted_value is not None and required_value is not None:
                    # 组内分隔线：不是最后一项时添加 HRFlowable 分隔线
                    # 分隔线使用 C_BORDER 浅色，厚度 0.3mm，视觉上区分各条违规
                    # 有精确数值时显示 "实际值 | 要求值 | 偏差" 三列
                    # 偏差 = 实际值 - 要求值，正值表示超出要求（过宽/过长），负值表示不足
                    diff = item.get("difference", "?")  # diff: item.get("difference", "?")
                    line = (
                        f"  实际值: {extracted_value}  |  "
                        f"要求值: {required_value}  |  "
                        f"偏差: {diff}"
                    )
                else:  # # 无精确值，显示说明
                    # 修正建议页：逐条展示修正建议，只在有建议时才生成
                    # 与违规详情页的关系：违规页展示问题，修正页展示方案
                    line = f"  {t("violation.explanation", lang)}: {explanation}"  # line: f"  {t("violation.explanation", lang)}:

                buf.append(
                    Paragraph(line, s["violation-detail"])
                )  # buf: buf.append(Paragraph(line, s['violation-detail']))

                # 置信度显示（P36）
                item_confidence = item.get("confidence")  # item_confidence: item.get("confidence")
                if item_confidence is not None and item_confidence > 0:
                    buf.append(  # buf: buf.append(
                        Paragraph(
                            # 修正建议的每条展示：标题含序号+条款ID+实体ID
                            # suggestion 来自 correction_engine 的输出，提供具体的修改建议
                            f"  {t("report.confidence", lang)}: {int(item_confidence * 100)}%",
                            s["violation-detail"],
                        )
                    )

                # 匹配修正建议
                # 按 entity_id 精确匹配优先，按 clause_id 模糊匹配兜底
                # 同一违规可能有多条建议，最多展示 2 条避免页面过长
                matched = [
                    c
                    for c in corrections  # # 遍历修正建议匹配
                    if c.get("entity_id") == entity_id
                    or c.get("clause_id") == clause_id  # # 按实体 ID 或条款 ID 匹配
                ]
                for c in matched[:2]:  # # 最多显示 2 条建议
                    suggestion = c.get("suggestion", c.get("description", ""))
                    if suggestion:  # # 有建议内容时显示
                        buf.append(  # buf: buf.append(
                            Paragraph(
                                f"  {t("violation.suggestion", lang)}: {suggestion[:100]}",
                                s["correction-text"],
                            )
                        )

                buf.append(Spacer(1, 4))  # buf: buf.append(Spacer(1, 4))
                if idx < len(items) - 1:
                    # 不是最后一项时加分隔线
                    # 组内最后一条不需要分隔线，因为页面底部已经有 PageBreak 或自然结束
                    buf.append(  # buf: buf.append(
                        HRFlowable(
                            width="100%",
                            color=C_BORDER,
                            thickness=0.3,
                        )
                    )
                    buf.append(Spacer(1, 4))  # buf: buf.append(Spacer(1, 4))

            page_count += 1  # page_count +: 1

    # page_count: 页码计数器

    # ══════════════════════════════════════════════════════
    # 修正建议页
    # ══════════════════════════════════════════════════════

    def _build_correction_pages(
        self,
        buf,
        corrections: List[Dict[str, Any]],
        lang: str = "zh",  # self, buf, corrections: List[Dict[str, Any]], lang: str: "zh"
    ):
        """修正建议页：逐条展示每条修正建议
        # 表格样式：斑马纹(偶数行浅灰)、表头蓝底白字、单元格内边距 6x4
        # GRID 0.3mm 边框、VALIGN MIDDLE 垂直居中、repeatRows=1 表头跨页重复
        # 这些样式命令按顺序应用到表格，后应用的覆盖先应用的

        只在有修正建议时才生成此页，避免空页浪费纸张。
        每条建议格式："#序号  条款ID | 实体ID" + 建议内容
        与违规详情页的关系：违规页展示问题，修正页展示方案。
        """
        if not corrections:  # corrections: 修正建议为空
            return

        s = self.styles
        # styles: 样式字典
        buf.append(PageBreak())  # buf: buf.append(PageBreak())
        buf.append(
            Paragraph(t("report.correction_title", lang), s["section-title"])
        )  # buf: buf.append(Paragraph(t('report.correction_title', lang), s['section-ti
        buf.append(Spacer(1, 4))  # buf: buf.append(Spacer(1, 4))
        buf.append(
            Paragraph(t("report.correction_count", lang, count=len(corrections)), s["body"])
        )  # buf.append(Paragraph(t("report.correction_count", lang, count: len(corrections)), s["body"]))
        # paragraph: 多语言文本
        buf.append(Spacer(1, 12))  # buf: buf.append(Spacer(1, 12))

        for idx, c in enumerate(corrections):  # # 遍历修正建议
            entity_id = c.get("entity_id", "")  # entity_id: c.get("entity_id", "")
            clause_id = c.get("clause_id", "")  # clause_id: c.get("clause_id", "")
            suggestion = c.get("suggestion", c.get("description", ""))

            buf.append(Paragraph(f"#{idx + 1}  {clause_id} | {entity_id}", s["violation-title"]))
            buf.append(
                Paragraph(suggestion, s["correction-text"])
            )  # buf: buf.append(Paragraph(suggestion, s['correction-text']))
            buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))
            buf.append(  # buf: buf.append(
                HRFlowable(
                    width="100%",
                    color=C_BORDER,
                    thickness=0.3,
                )
            )
            buf.append(Spacer(1, 6))  # buf: buf.append(Spacer(1, 6))

    # ══════════════════════════════════════════════════════
    # 工具方法
    # ══════════════════════════════════════════════════════

    def _make_table(self, rows, col_widths, headers=None):
        """创建格式化表格

        斑马纹设计：偶数行浅灰背景(#F5F7FA)，奇数行白色，提高长表格可读性
        表头使用 C_PRIMARY 蓝色背景 + 白色文字，视觉区分明显
        repeatRows=1 确保表头在多页表格中每页重复显示  # repeatRows: 1 确保表头在多页表格中每页重复显示
        """
        data = []  # data: []
        if headers:  # headers: 表格表头
            header_paras = [
                Paragraph(h, self.styles["table-header"]) for h in headers
            ]  # header_paras: [Paragraph(h, self.styles["table-header"
            # header_paras: 表头 Paragraph
            data.append(header_paras)
        # data: 追加表格行

        for row in rows:  # rows: 表格数据行
            cell_paras = []  # cell_paras: []
            for i, cell in enumerate(row):  # enumerate: 构建每行单元格
                cell_paras.append(Paragraph(str(cell), self.styles["table-cell"]))
            # cell_paras: 追加单元格
            data.append(cell_paras)
        # data: 追加表格行

        t = Table(data, colWidths=col_widths, repeatRows=1 if headers else 0)
        # t: ReportLab Table 实例
        style_cmds = [  # style_cmds: ReportLab TableStyle 命令列表
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if headers:  # headers: 表格表头
            style_cmds.append(("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY))
            style_cmds.append(("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE))
        # 斑马纹：偶数行（row index 2,4,6...）浅灰背景
        # 从 row 1 开始（row 0 是表头），row 1 是白色，row 2 是浅灰，交替
        for i in range(1, len(data)):  # range: 斑马纹行索引
            if i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), C_BG_LIGHT))

        t.setStyle(TableStyle(style_cmds))
        # t: 应用 TableStyle
        return t


# return:
