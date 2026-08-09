"""封面页 — 项目信息 + 统计概览"""

import datetime
from typing import Any, Dict, List

from .components import (
    Paragraph, Spacer, ColorBar, StatCard,
    C_PRIMARY, C_TEXT, C_TEXT_LIGHT, C_DANGER, C_ACCENT,
)


def build_cover(
    buf: List[Any],
    styles: Dict[str, Any],
    page_w: float,
    margin: float,
    filename: str,
    summary: Dict[str, Any],
    lang: str = "zh",
) -> None:
    """封面页：标题 + 项目信息 + 统计卡片"""
    s = styles
    cw = page_w - 2 * margin

    buf.append(Spacer(1, 60))
    buf.append(ColorBar(cw, height=120, color=C_PRIMARY))
    buf.append(Spacer(1, 8))

    buf.append(Paragraph("BAA 合规审查报告", s["cover-title"]))
    buf.append(Spacer(1, 6))
    buf.append(Paragraph(f"文件名：{filename}", s["cover-sub"]))

    building_type = summary.get("building_type", "civil")
    type_label = (
        "民用建筑" if building_type == "civil" else "工业建筑"
    )
    buf.append(Paragraph(f"建筑类型：{type_label}", s["cover-info"]))

    now = datetime.datetime.now()
    buf.append(Paragraph(f"生成时间：{now.strftime('%Y-%m-%d %H:%M')}", s["cover-info"]))
    buf.append(Paragraph("Blueprint AI Agent", s["cover-info"]))
    buf.append(Spacer(1, 24))

    violations = summary.get("violations", 0)
    total_entities = summary.get("total_entities", 0)
    total_checks = summary.get("total_checks", 0)
    violation_by_clause = summary.get("violation_by_clause", {})
    card_w = (cw - 24) / 4

    card_data = [
        ("违规总数", str(violations), C_DANGER),
        ("检查图元", str(total_entities), C_PRIMARY),
        ("检查项次", str(total_checks), C_PRIMARY),
        ("涉及条款", str(len(violation_by_clause)), C_ACCENT),
    ]
    for label, value, color in card_data:
        buf.append(StatCard(label, value, color, card_w))
        buf.append(Spacer(1, 8))

    buf.append(Spacer(1, 30))
    stats_lines = [
        f"<b>违规总数:</b> {violations}",
        f"<b>检查图元:</b> {total_entities}",
        f"<b>检查项次:</b> {total_checks}",
        f"<b>涉及条款:</b> {len(violation_by_clause)}",
    ]
    for line in stats_lines:
        buf.append(Paragraph(line, s["cover-sub"]))
        buf.append(Spacer(1, 6))

    buf.append(Spacer(1, 60))
    buf.append(Paragraph("本报告由 BAA 自动生成，仅供审查参考，不替代人工审核。", s["footer"]))