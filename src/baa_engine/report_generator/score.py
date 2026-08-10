"""合规度评分页 — 总体评分 + 合规率 + 严重级别分布 + 违规分类条状图"""

from typing import Any, Dict, List

from .components import (
    Paragraph, Spacer, StatCard, make_table,
    C_ACCENT, C_PRIMARY, C_WARNING, C_DANGER,
)


def _build_category_bar(buf: List[Any], details: List[Dict[str, Any]], cw: float, s: Dict[str, Any]) -> None:
    """P94: 违规分类条状图（按 category 聚合，纯文本+Paragraph 实现，稳定无绘图开销）"""
    from collections import Counter

    cats = Counter(d.get("category", "未分类") for d in details)
    if not cats:
        return

    total = sum(cats.values())
    top_cats = cats.most_common(8)
    max_count = top_cats[0][1] if top_cats else 1
    bar_max_w = cw - 200

    for cat, count in top_cats:
        pct = count / total * 100
        bar_len = max(1, int(bar_max_w * count / max_count))
        # 用色块字符模拟进度条
        bar = "█" * min(40, max(1, int(bar_len / (bar_max_w / 40))))
        bar_pct = f"{pct:.1f}%"
        buf.append(Paragraph(
            f"<b>{cat}</b>  {'█' * min(30, max(1, int(30 * count / max_count)))} {count} ({bar_pct})",
            s["body"],
        ))
        buf.append(Spacer(1, 2))


def build_score_page(
    buf: List[Any],
    styles: Dict[str, Any],
    page_w: float,
    margin: float,
    summary: Dict[str, Any],
    lang: str = "zh",
    details: List[Dict[str, Any]] = None,
) -> None:
    """合规度评分页"""
    s = styles
    cw = page_w - 2 * margin
    details = details or []

    buf.append(Paragraph("审查评分", s["section-title"]))
    buf.append(Spacer(1, 8))

    # 总体评分
    overall_score = summary.get("overall_score", summary.get("score"))
    if overall_score is not None:
        card_w = (cw - 16) / 2
        if overall_score >= 90:
            score_color, score_label = C_ACCENT, "优秀"
        elif overall_score >= 70:
            score_color, score_label = C_PRIMARY, "良好"
        elif overall_score >= 50:
            score_color, score_label = C_WARNING, "一般"
        else:
            score_color, score_label = C_DANGER, "不合格"
        buf.append(StatCard("合规度评分", f"{int(overall_score)}", score_color, card_w, 70))
        buf.append(Spacer(1, 6))
        buf.append(Paragraph(f"等级：{score_label} ({overall_score:.1f}/100)", s["body"]))
        buf.append(Spacer(1, 12))

    # 合规率
    compliance_rate = summary.get("compliance_rate", 0.0)
    if isinstance(compliance_rate, float):
        compliance_pct = int(compliance_rate * 100)
    else:
        compliance_pct = compliance_rate
    if compliance_pct != 0:
        card_w = (cw - 16) / 2
        cr_color = (
            C_ACCENT if compliance_pct >= 80
            else (C_WARNING if compliance_pct >= 50 else C_DANGER)
        )
        buf.append(StatCard("通过率", f"{compliance_pct}%", cr_color, card_w, 70))
        buf.append(Spacer(1, 6))
        buf.append(Paragraph(f"通过率：{compliance_pct}%", s["body"]))
        buf.append(Spacer(1, 16))

    # 严重级别分布
    severity_dist = summary.get("severity_distribution", {})
    if severity_dist:
        buf.append(Paragraph("违规分布 - 按类型", s["subsection-title"]))
        buf.append(Spacer(1, 6))
        sev_map = {"critical": "严重", "major": "较大", "minor": "一般"}
        rows = [[sev_map.get(k, k), str(v)] for k, v in sorted(severity_dist.items())]
        buf.append(make_table(styles, rows, col_widths=[cw - 80, 80], headers=["严重级别", "数量"]))
        buf.append(Spacer(1, 16))

    # 实体类型分布
    entity_types = summary.get("entity_types", {})
    if entity_types:
        buf.append(Paragraph("实体类型分布", s["subsection-title"]))
        buf.append(Spacer(1, 6))
        rows = sorted(entity_types.items(), key=lambda x: -x[1])
        buf.append(make_table(styles, [list(r) for r in rows], col_widths=[cw - 80, 80],
                              headers=["实体类型", "数量"]))

    # 平均置信度
    avg_confidence = summary.get("avg_confidence")
    if avg_confidence is not None and avg_confidence > 0:
        buf.append(Spacer(1, 12))
        card_w = (cw - 16) / 2
        conf_color = (
            C_ACCENT if avg_confidence >= 0.85
            else (C_WARNING if avg_confidence >= 0.6 else C_DANGER)
        )
        buf.append(StatCard("平均置信度", f"{int(avg_confidence * 100)}%", conf_color, card_w, 70))

    # P94: 违规分类分布条状图（有违规数据时展示）
    if details:
        buf.append(Spacer(1, 16))
        buf.append(Paragraph("违规分类分布", s["subsection-title"]))
        buf.append(Spacer(1, 6))
        _build_category_bar(buf, details, cw, s)