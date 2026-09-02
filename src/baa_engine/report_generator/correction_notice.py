"""
整改通知单 PDF 生成器（P119 续）

仅包含 audit.status=confirmed 的违规条目，按 function_id 分组输出。
每页含封面 + 分组整改清单 + 签字页。
"""

import datetime
import uuid
from typing import Any, Dict, List

from reportlab.lib.styles import ParagraphStyle

from .components import (
    Paragraph,
    Spacer,
    PageBreak,
    StatCard,
    C_PRIMARY,
    C_TEXT,
    C_TEXT_LIGHT,
    C_DANGER,
    C_ACCENT,
    C_WARNING,
    build_styles,
    build_doc,
    make_table,
    HRFlowable,
)


def build_correction_notice(
    items: List[Dict[str, Any]],
    review_meta: Dict[str, Any],
    output_path: Any = None,
) -> bytes:
    """
    生成整改通知单 PDF

    Args:
        items: get_confirmed_items() 返回的列表，每条含 id/review_id/function_id/entity_id/status/note/reason
        review_meta: 审查元信息 {drawing_name, project_id, team_id, reviewer, date}

    Returns:
        PDF bytes
    """
    styles = build_styles()
    from reportlab.lib.pagesizes import A4 as _A4
    page_w, page_h = _A4  # 595 × 842 points
    from reportlab.lib.units import mm
    margin = 20 * mm  # 20mm in points

    buf: List[Any] = []

    _build_cover_page(buf, styles, page_w, margin, items, review_meta)
    buf.append(PageBreak())
    _build_grouped_notices(buf, styles, page_w, margin, items)
    buf.append(PageBreak())
    _build_sign_page(buf, styles, page_w, margin)

    return build_doc(page_w, 842.0, margin, output_path, buf)


def _build_cover_page(
    buf: List[Any],
    styles: Dict[str, Any],
    page_w: float,
    margin: float,
    items: List[Dict[str, Any]],
    review_meta: Dict[str, Any],
) -> None:
    """整改通知单封面"""
    s = styles
    cw = page_w - 2 * margin

    buf.append(Spacer(1, 60))
    buf.append(Paragraph("整改通知单", s["cover-title"]))
    buf.append(Spacer(1, 4))
    buf.append(Paragraph(
        "CORRECTION NOTICE",
        ParagraphStyle("notice-sub", fontName="Helvetica", fontSize=12, textColor=C_TEXT_LIGHT, alignment=1),
    ))
    buf.append(Spacer(1, 24))

    notice_id = review_meta.get("notice_id", f"CN-{uuid.uuid4().hex[:8].upper()}")
    buf.append(Paragraph(f"编号：{notice_id}", s["cover-info"]))
    buf.append(Paragraph(f"项目名称：{review_meta.get('project_name', '未指定')}", s["cover-info"]))
    buf.append(Paragraph(f"图纸名称：{review_meta.get('drawing_name', '未指定')}", s["cover-info"]))
    buf.append(Paragraph(f"审查人：{review_meta.get('reviewer', '系统')}", s["cover-info"]))

    now = datetime.datetime.now()
    buf.append(Paragraph(f"生成日期：{now.strftime('%Y-%m-%d %H:%M')}", s["cover-info"]))
    buf.append(Spacer(1, 24))

    # 统计卡片
    by_func = _group_by_func(items)
    func_count = len(by_func)
    entities = {it.get("entity_id", "") for it in items if it.get("entity_id")}

    card_w = (cw - 48) / 3
    cards = [
        StatCard("确认违规", str(len(items)), C_DANGER, card_w),
        StatCard("涉及条款", str(func_count), C_WARNING, card_w),
        StatCard("涉及图元", str(len(entities)), C_ACCENT, card_w),
    ]
    buf.extend(cards)
    buf.append(Spacer(1, 30))

    buf.append(Paragraph(
        "<b>说明：</b>本通知单列出了经审查确认后需要整改的违规条目。请项目负责人按照规范要求完成整改，并在复查栏签署意见。",
        ParagraphStyle("notice-desc", parent=s["body"], fontSize=9, textColor=C_TEXT_LIGHT, leading=14),
    ))


def _group_by_func(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """按 function_id 分组"""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        fid = it.get("function_id", "UNKNOWN") or "UNKNOWN"
        groups.setdefault(fid, []).append(it)
    return groups


def _build_grouped_notices(
    buf: List[Any],
    styles: Dict[str, Any],
    page_w: float,
    margin: float,
    items: List[Dict[str, Any]],
) -> None:
    """按条款分组的整改清单"""
    s = styles
    cw = page_w - 2 * margin
    by_func = _group_by_func(items)

    seq = 0
    for fid in sorted(by_func.keys()):
        entries = by_func[fid]
        seq += 1

        buf.append(Spacer(1, 14))
        buf.append(Paragraph(
            f"第 {seq} 项：{fid} ({len(entries)} 处)",
            ParagraphStyle("notice-section", fontName="Helvetica-Bold", fontSize=11, textColor=C_PRIMARY),
        ))
        buf.append(Spacer(1, 4))

        # 整改表格
        table_data = [["序号", "图元 ID", "批注", "整改要求"]]
        for i, it in enumerate(entries):
            entity_id = it.get("entity_id", "") or "—"
            note = it.get("note", "") or "—"
            fix = f"按 {fid} 要求整改"
            table_data.append([str(i + 1), str(entity_id), str(note), str(fix)])
        table_data.append(["", "", "", ""])  # 空行留白

        # make_table(styles, rows, col_widths, headers=None)
        tbl = make_table(
            s,
            table_data,
            col_widths=[40, cw * 0.25, cw * 0.35, cw * 0.35],
        )
        buf.append(tbl)
        buf.append(Spacer(1, 8))

        # 复查栏
        buf.append(Paragraph("复查：", s["body"]))
        buf.append(Spacer(1, 12))
        buf.append(HRFlowable(width="100%", color=C_TEXT_LIGHT, thickness=0.3))
        buf.append(Spacer(1, 4))
        buf.append(Paragraph("签字：___________    日期：___________", ParagraphStyle("sign", parent=s["body"], fontSize=9, textColor=C_TEXT_LIGHT)))
        buf.append(Spacer(1, 16))

    if seq > 0:
        buf.append(Spacer(1, 20))


def _build_sign_page(
    buf: List[Any],
    styles: Dict[str, Any],
    page_w: float,
    margin: float,
) -> None:
    """签字页"""
    s = styles
    cw = page_w - 2 * margin

    buf.append(Spacer(1, 20))
    buf.append(Paragraph("项目负责人确认", s["section-title"]))
    buf.append(Spacer(1, 10))
    buf.append(Paragraph("本人已确认上述整改内容，将按要求完成整改。", s["body"]))
    buf.append(Spacer(1, 20))
    buf.append(Paragraph("签字：_____________________", s["body"]))
    buf.append(Spacer(1, 12))
    buf.append(Paragraph("日期：_____________________", s["body"]))
    buf.append(Spacer(1, 20))

    buf.append(HRFlowable(width="100%", color=C_TEXT_LIGHT, thickness=0.3))
    buf.append(Spacer(1, 8))
    buf.append(Paragraph("BAA 合规审查系统自动生成 · 请打印后签署", ParagraphStyle("footer-note", parent=s["body"], fontSize=8, textColor=C_TEXT_LIGHT, alignment=1)))