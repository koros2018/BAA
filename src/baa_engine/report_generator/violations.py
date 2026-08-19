"""违规详情页 + 修正建议页 — 按条款分组展示"""

from typing import Any, Dict, List

from .components import (
    Paragraph,
    Spacer,
    HRFlowable,
    C_DANGER,
    C_WARNING,
    C_PRIMARY,
    C_ACCENT,
    C_BORDER,
)


def build_violation_pages(
    buf: List[Any],
    styles: Dict[str, Any],
    details: List[Dict[str, Any]],
    corrections: List[Dict[str, Any]],
    lang: str = "zh",
) -> None:
    """违规详情页：按 clause_id 分组，每组一页（P94: 增强布局 + 位置/严重度/置信度可视化）"""
    if not details:
        return

    s = styles

    # 按 clause_id 分组
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for d in details:
        grouped.setdefault(d.get("clause_id", "unknown"), []).append(d)

    page_count = 0
    for clause_id, items in grouped.items():
        clause_title = items[0].get("clause_title", "")
        title = f"{clause_id} — {clause_title}" if clause_id else clause_title

        if page_count > 0:
            buf.append(Spacer(1, 12))
            buf.append(HRFlowable(width="100%", color=C_BORDER, thickness=0.5))
        buf.append(Paragraph(title, s["section-title"]))
        buf.append(Spacer(1, 6))

        for idx, item in enumerate(items):
            entity_id = item.get("entity_id", "")
            entity_type = item.get("entity_type", "")
            result = item.get("result", "")
            extracted_value = item.get("extracted_value")
            required_value = item.get("required_value")
            explanation = item.get("explanation", "")
            severity = item.get("severity", "minor")
            confidence = item.get("confidence", 0.0)

            # 严重度标签
            severity_map = {
                "critical": ("严重", C_DANGER),
                "major": ("较大", C_WARNING),
                "minor": ("一般", C_PRIMARY),
            }
            sev_label, sev_color = severity_map.get(severity, ("一般", C_PRIMARY))

            # 置信度标签
            conf_label = "高" if confidence >= 0.85 else ("中" if confidence >= 0.6 else "低")
            conf_color = (
                C_ACCENT if confidence >= 0.85 else (C_WARNING if confidence >= 0.6 else C_DANGER)
            )

            # 实体位置
            location = item.get("location", item.get("bbox", {}))
            loc_str = ""
            if isinstance(location, dict):
                x = location.get("x", location.get("center_x"))
                y = location.get("y", location.get("center_y"))
                if x is not None and y is not None:
                    loc_str = f"位置: ({x:.0f}, {y:.0f})"

            num = idx + 1
            result_label = "不合规" if "FAIL" in str(result) else "警告"
            result_color = C_DANGER if "FAIL" in str(result) else C_WARNING

            # 标题行：编号 + 实体 + 严重度 + 置信度 + 结果
            buf.append(
                Paragraph(
                    f"#{num}  [{entity_type}] {entity_id}  "
                    f'<font color="{sev_color.hexval()}">[{sev_label}]</font>  '
                    f'<font color="{conf_color.hexval()}">置信度{conf_label}</font>  '
                    f'<font color="{result_color.hexval()}">{result_label}</font>',
                    s["violation-title"],
                )
            )

            # 详情行：实际值 vs 要求值 + 偏差 + 位置
            detail_lines = []
            if extracted_value is not None and required_value is not None:
                diff = item.get("difference", "?")
                detail_lines.append(
                    f"实际值: {extracted_value}  |  要求值: {required_value}  |  偏差: {diff}"
                )
            else:
                detail_lines.append(f"说明: {explanation}")

            if loc_str:
                detail_lines.append(loc_str)

            for line in detail_lines:
                buf.append(Paragraph(line, s["violation-detail"]))

            # 匹配修正建议
            matched = [
                c
                for c in corrections
                if c.get("entity_id") == entity_id or c.get("clause_id") == clause_id
            ]
            for c in matched[:2]:
                suggestion = c.get("suggestion", c.get("description", ""))
                if suggestion:
                    buf.append(Paragraph(f"建议: {suggestion[:150]}", s["correction-text"]))

            buf.append(Spacer(1, 4))
            if idx < len(items) - 1:
                buf.append(HRFlowable(width="100%", color=C_BORDER, thickness=0.3))
                buf.append(Spacer(1, 4))

        page_count += 1


def build_correction_pages(
    buf: List[Any],
    styles: Dict[str, Any],
    corrections: List[Dict[str, Any]],
    lang: str = "zh",
) -> None:
    """修正建议页：逐条展示"""
    if not corrections:
        return

    s = styles
    buf.append(Spacer(1, 16))
    buf.append(Paragraph("修正建议", s["section-title"]))
    buf.append(Spacer(1, 4))
    buf.append(Paragraph(f"共 {len(corrections)} 条建议", s["body"]))
    buf.append(Spacer(1, 12))

    for idx, c in enumerate(corrections):
        entity_id = c.get("entity_id", "")
        clause_id = c.get("clause_id", "")
        suggestion = c.get("suggestion", c.get("description", ""))

        buf.append(Paragraph(f"#{idx + 1}  {clause_id} | {entity_id}", s["violation-title"]))
        buf.append(Paragraph(suggestion, s["correction-text"]))
        buf.append(Spacer(1, 6))
        buf.append(HRFlowable(width="100%", color=C_BORDER, thickness=0.3))
        buf.append(Spacer(1, 6))
