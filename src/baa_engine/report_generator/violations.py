"""违规详情页 + 修正建议页 — 按条款分组展示"""

from typing import Any, Dict, List

from .components import (
    Paragraph, Spacer, HRFlowable,
    C_DANGER, C_WARNING, C_BORDER,
)


def build_violation_pages(
    buf: List[Any],
    styles: Dict[str, Any],
    details: List[Dict[str, Any]],
    corrections: List[Dict[str, Any]],
    lang: str = "zh",
) -> None:
    """违规详情页：按 clause_id 分组，每组一页"""
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

            num = idx + 1
            result_label = "不合规" if "FAIL" in str(result) else "警告"
            result_color = C_DANGER if "FAIL" in str(result) else C_WARNING

            buf.append(Paragraph(
                f"#{num}  [{entity_type}] {entity_id} "
                f'<font color="{result_color.hexval()}">{result_label}</font>',
                s["violation-title"],
            ))

            if extracted_value is not None and required_value is not None:
                diff = item.get("difference", "?")
                line = f"  实际值: {extracted_value}  |  要求值: {required_value}  |  偏差: {diff}"
            else:
                line = f"  说明: {explanation}"
            buf.append(Paragraph(line, s["violation-detail"]))

            # 置信度
            item_confidence = item.get("confidence")
            if item_confidence is not None and item_confidence > 0:
                buf.append(Paragraph(f"  置信度: {int(item_confidence * 100)}%", s["violation-detail"]))

            # 匹配修正建议
            matched = [
                c for c in corrections
                if c.get("entity_id") == entity_id or c.get("clause_id") == clause_id
            ]
            for c in matched[:2]:
                suggestion = c.get("suggestion", c.get("description", ""))
                if suggestion:
                    buf.append(Paragraph(f"  建议: {suggestion[:100]}", s["correction-text"]))

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