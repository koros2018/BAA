# -*- coding: utf-8 -*-
"""报告产品化补页（Roadmap v4 T-B4）：条款索引页 / 结论页 / 签字页。

与 report_generator 既有页面同风格（reportlab Flowable + build_styles），
由 main.generate() 在违规详情之后追加编排。
"""

from typing import Any, Dict, List

from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle

from .components import C_PRIMARY, ColorBar


def build_toc_page(
    buf, styles, page_w, margin, details: List[Dict[str, Any]], lang: str = "zh"
) -> None:
    """条款索引页：违规涉及条款 → 标题 / 严重度 / 出现次数（审图定位入口）。"""
    buf.append(ColorBar(page_w - 2 * margin, height=60, color=C_PRIMARY))
    buf.append(Spacer(1, 6 * mm))
    buf.append(Paragraph("条款索引" if lang == "zh" else "Clause Index", styles["section-title"]))
    buf.append(Spacer(1, 3 * mm))
    buf.append(
        Paragraph(
            (
                "按条款编号汇总本报告涉及的全部审查条款；详情页码见违规详情章节。"
                if lang == "zh"
                else "All clauses cited in this report, grouped by clause id."
            ),
            styles["body-small"],
        )
    )
    buf.append(Spacer(1, 4 * mm))

    rows: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for d in details:
        cid = str(d.get("clause_id", "-"))
        if cid not in rows:
            rows[cid] = {
                "title": d.get("clause_title") or d.get("title", ""),
                "severity": d.get("severity", ""),
                "count": 0,
                "standard": d.get("standard", ""),
            }
            order.append(cid)
        rows[cid]["count"] += 1

    data = [
        [
            "条款编号" if lang == "zh" else "Clause",
            "条款标题" if lang == "zh" else "Title",
            "规范" if lang == "zh" else "Standard",
            "最高严重度" if lang == "zh" else "Severity",
            "出现次数" if lang == "zh" else "Count",
        ]
    ]
    for cid in sorted(order):
        r = rows[cid]
        data.append([cid, r["title"][:38], r["standard"], r["severity"], str(r["count"])])
    if len(data) == 1:
        data.append(
            ["-" if lang == "zh" else "-", "无违规条款" if lang == "zh" else "None", "", "", ""]
        )

    t = Table(data, colWidths=[28 * mm, 62 * mm, 22 * mm, 22 * mm, 18 * mm], repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "WQY"),
                ("BACKGROUND", (0, 0), (-1, 0), ("#1a3a6b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), ("white")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, "#c8d2e0"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), ["white", "#f2f5fa"]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    buf.append(t)


def build_conclusion_page(
    buf,
    styles,
    page_w,
    margin,
    filename: str,
    summary: Dict[str, Any],
    details: List[Dict[str, Any]],
    lang: str = "zh",
) -> None:
    """结论页：综合结论 + 严重度分布 + 整改路径建议。"""
    buf.append(ColorBar(page_w - 2 * margin, height=60, color=C_PRIMARY))
    buf.append(Spacer(1, 6 * mm))
    buf.append(Paragraph("审查结论" if lang == "zh" else "Conclusion", styles["section-title"]))
    buf.append(Spacer(1, 4 * mm))

    total = len(details)
    sev: Dict[str, int] = {}
    for d in details:
        s = str(d.get("severity", "unknown"))
        sev[s] = sev.get(s, 0) + 1
    critical = sev.get("critical", 0)

    if total == 0:
        verdict = "经审查，未发现违反现行规范条款的情形，图纸审查通过。"
    elif critical == 0:
        verdict = (
            "经审查，发现 %d 项提示类问题（无强制性条款违规），建议按提示逐项复核后通过。" % total
        )
    else:
        verdict = (
            "经审查，发现 %d 项违规（其中强制性 %d 项），"
            "本图当前状态不符合审查通过条件，须完成整改并复核后重新提交。" % (total, critical)
        )
    buf.append(Paragraph(verdict, styles["body"]))
    buf.append(Spacer(1, 4 * mm))

    sev_rows = [
        [
            "严重度" if lang == "zh" else "Severity",
            "critical（强制）" if lang == "zh" else "critical",
            "major（较大）" if lang == "zh" else "major",
            "minor（一般）" if lang == "zh" else "minor",
            "合计" if lang == "zh" else "Total",
        ],
        [
            "数量" if lang == "zh" else "Count",
            str(sev.get("critical", 0)),
            str(sev.get("major", 0)),
            str(sev.get("minor", 0)),
            str(total),
        ],
    ]
    t = Table(sev_rows, colWidths=[30 * mm] + [28 * mm] * 4)
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "WQY"),
                ("BACKGROUND", (0, 0), (-1, 0), ("#eef2f8")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, "#c8d2e0"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    buf.append(t)
    buf.append(Spacer(1, 4 * mm))
    path_txt = (
        "整改路径：① 按「整改优先级」章节处理 critical/high 违规 → ② "
        "修正图纸后重新上传复核 → ③ 复核通过后于本页签字归档。"
        if lang == "zh"
        else "Rectification: fix critical/high items, re-upload for re-review, then sign and archive."
    )
    buf.append(Paragraph(path_txt, styles["body-small"]))


def build_signature_page(
    buf, styles, page_w, margin, summary: Dict[str, Any], lang: str = "zh"
) -> None:
    """签字页：编制/审核/批准签栏 + 项目信息 + 免责声明。"""
    buf.append(PageBreak())
    buf.append(ColorBar(page_w - 2 * margin, height=60, color=C_PRIMARY))
    buf.append(Spacer(1, 8 * mm))
    buf.append(Paragraph("签署与归档" if lang == "zh" else "Sign-off", styles["section-title"]))
    buf.append(Spacer(1, 5 * mm))

    info = [
        [
            "项目文件" if lang == "zh" else "File",
            str(summary.get("filename", summary.get("file", "-"))),
        ],
        ["建筑类型" if lang == "zh" else "Building", str(summary.get("building_type", "-"))],
        [
            "审查时间" if lang == "zh" else "Reviewed at",
            str(summary.get("reviewed_at", summary.get("generated_at", "-"))),
        ],
        ["审查引擎" if lang == "zh" else "Engine", "Blueprint AI Agent"],
    ]
    t_info = Table(info, colWidths=[34 * mm, 96 * mm])
    t_info.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "WQY"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, "#c8d2e0"),
                ("BACKGROUND", (0, 0), (0, -1), ("#eef2f8")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    buf.append(t_info)
    buf.append(Spacer(1, 10 * mm))

    roles = [
        "编制（审查引擎）" if lang == "zh" else "Prepared by",
        "审核" if lang == "zh" else "Reviewed by",
        "批准" if lang == "zh" else "Approved by",
    ]
    t_sign = Table(
        [
            [r, "签名：" if lang == "zh" else "Signature:", "日期：" if lang == "zh" else "Date:"]
            for r in roles
        ],
        colWidths=[42 * mm, 48 * mm, 40 * mm],
        rowHeights=[14 * mm] * 3,
    )
    t_sign.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "WQY"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, "#8a9ab0"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (0, -1), ("#eef2f8")),
            ]
        )
    )
    buf.append(t_sign)
    buf.append(Spacer(1, 8 * mm))
    buf.append(
        Paragraph(
            (
                "免责声明：本报告由 AI 审查引擎自动生成，供设计校核参考，"
                "不替代法定施工图审查机构出具的审查意见。"
                if lang == "zh"
                else "Disclaimer: auto-generated by AI review engine; not a substitute for statutory review."
            ),
            styles["body-small"],
        )
    )
