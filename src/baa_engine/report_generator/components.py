"""
PDF 报告组件 — 字体注册 / 颜色常量 / Flowable 自定义组件 / 表格工具
"""

import datetime
import os
import tempfile
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
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
C_WHITE = colors.white

# ── 字体注册 ─────────────────────────────────────────────
_FONT_REGISTERED = False


def ensure_font() -> None:
    """注册 CJK 字体（幂等；候选字体不可用时自动尝试下一个）"""
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    ttf_path = os.environ.get("BAA_PDF_FONT")
    candidates = [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttf",
        "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/tmp/wqy-zenhei.ttf",
        # Windows 系统中文字体（微软雅黑 / 黑体 / 宋体）
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        # macOS 系统中文字体（TrueType 轮廓优先: reportlab TTFont 不支持
        # CFF/PostScript 轮廓，苹方/冬青黑体均为 CFF，只能作末位候选）
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]
    if ttf_path:
        # 环境变量显式指定: 路径不存在直接报错，不回退候选列表
        if not os.path.exists(ttf_path):
            raise RuntimeError(
                f"CJK font not found at {ttf_path}. Install WenQuanYi or set BAA_PDF_FONT."
            )
        pdfmetrics.registerFont(TTFont("WQY", ttf_path))
    else:
        for p in candidates:
            if not os.path.exists(p):
                continue
            try:
                pdfmetrics.registerFont(TTFont("WQY", p))
                ttf_path = p
                break
            except Exception as exc:  # noqa: BLE001 — CFF 轮廓/损坏字体等一律跳过
                print(f"[ensure_font] 字体不可用，跳过 {p}: {exc}")
        if not ttf_path:
            raise RuntimeError(
                "CJK font not found (all candidates missing or unusable). "
                "Install WenQuanYi or set BAA_PDF_FONT."
            )
    pdfmetrics.registerFont(TTFont("WQY-Bold", ttf_path))
    _FONT_REGISTERED = True


# ── Flowable 自定义组件 ──────────────────────────────────


class ColorBar(Flowable):
    """顶部彩色标题栏"""

    def __init__(self, width: float, height: float = 60, color=...) -> None:
        """初始化实例。"""
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.color = color

    def draw(self) -> None:
        """绘制组件到画布。"""
        self.canv.setFillColor(self.color)
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)


class StatCard(Flowable):
    """统计指标卡片"""

    def __init__(
        self,
        label: str,
        value: str,
        color: Any,
        width: float,
        height: float = 50,
    ) -> None:
        """初始化实例。"""
        Flowable.__init__(self)
        self.label = label
        self.value = value
        self.color = color
        self.width = width
        self.height = height

    def draw(self) -> None:
        """绘制组件到画布。"""
        c = self.canv
        c.setFillColor(self.color)
        c.setFont("WQY", 24)
        c.drawString(8, self.height - 32, self.value)
        c.setFillColor(C_TEXT_LIGHT)
        c.setFont("WQY", 9)
        c.drawString(8, 6, self.label)


# ── 样式构建 ─────────────────────────────────────────────


def build_styles(
    primary_hex: Optional[str] = None,
    secondary_hex: Optional[str] = None,
) -> Dict[str, ParagraphStyle]:
    """构建 PDF 段落样式字典。D3-T1 新增：模板可覆盖主/次色调。"""
    p_colors = colors.HexColor(primary_hex) if primary_hex else C_PRIMARY
    s_colors = colors.HexColor(secondary_hex) if secondary_hex else C_SECONDARY
    return {
        "cover-title": ParagraphStyle(
            "CoverTitle",
            fontName="WQY",
            fontSize=28,
            textColor=p_colors,
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
            textColor=p_colors,
            leading=22,
            spaceAfter=10,
        ),
        "subsection-title": ParagraphStyle(
            "SubsectionTitle",
            fontName="WQY",
            fontSize=13,
            textColor=s_colors,
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
    }


# ── 工具方法 ─────────────────────────────────────────────


def make_table(
    styles: Dict[str, ParagraphStyle],
    rows: List[List[Any]],
    col_widths: List[float],
    headers: Optional[List[str]] = None,
) -> Table:
    """创建格式化表格（斑马纹 + 表头蓝底白字）"""
    data: List[List[Any]] = []
    if headers:
        header_paras = [Paragraph(h, styles["table-header"]) for h in headers]
        data.append(header_paras)
    for row in rows:
        cell_paras = [Paragraph(str(cell), styles["table-cell"]) for cell in row]
        data.append(cell_paras)

    tbl = Table(data, colWidths=col_widths, repeatRows=1 if headers else 0)
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
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), C_BG_LIGHT))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


# ── 文档模板构建 ─────────────────────────────────────────


def build_doc(
    page_w: float,
    page_h: float,
    margin: float,
    output_path: Optional[str],
    buf: List[Any],
) -> bytes:
    """用 buf 流式内容构建 PDF 文档并返回字节"""
    tmp_path: Optional[str] = None
    if output_path:
        target = output_path
    else:
        # 无显式路径时用唯一临时文件（避免 /tmp 硬编码与并发覆盖）
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf", prefix="baa_report_")
        os.close(fd)
        target = tmp_path
    doc = BaseDocTemplate(
        target,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )
    frame = Frame(
        margin,
        margin,
        page_w - 2 * margin,
        page_h - 2 * margin,
        id="normal",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=frame)])
    doc.build(buf)
    with open(target, "rb") as f:
        data = f.read()
    if tmp_path:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    return data
