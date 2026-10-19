# -*- coding: utf-8 -*-
"""审查报告 Excel 导出（Roadmap v4 T-B4）：openpyxl 三 sheet（汇总/条款索引/违规明细）。"""

import io
from typing import Any, Dict, List

_SEV_FILL = {
    "critical": "C0392B",
    "major": "D35400",
    "minor": "27AE60",
}


def build_review_xlsx(
    review_id: str,
    filename: str,
    summary: Dict[str, Any],
    details: List[Dict[str, Any]],
) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    head_fill = PatternFill("solid", start_color="1A3A6B")
    head_font = Font(color="FFFFFF", bold=True)
    center = Alignment(horizontal="center", vertical="center")

    # Sheet1 汇总
    ws = wb.active
    ws.title = "汇总"
    total = len(details)
    sev: Dict[str, int] = {}
    for d in details:
        s = str(d.get("severity", "unknown"))
        sev[s] = sev.get(s, 0) + 1
    critical = sev.get("critical", 0)
    if total == 0:
        verdict = "未发现违规，审查通过。"
    elif critical == 0:
        verdict = f"发现 {total} 项提示类问题（无强制性违规），建议复核后通过。"
    else:
        verdict = f"发现 {total} 项违规（强制性 {critical} 项），须整改后重新提交。"

    rows = [
        ("项目文件", filename),
        ("审查引擎", "Blueprint AI Agent"),
        ("报告 ID", review_id),
        ("违规总数", total),
        ("critical", sev.get("critical", 0)),
        ("major", sev.get("major", 0)),
        ("minor", sev.get("minor", 0)),
        ("审查结论", verdict),
        ("免责声明", "AI 自动生成，供设计校核参考，不替代法定审查意见。"),
    ]
    for r, (k, v) in enumerate(rows, start=1):
        ws.cell(r, 1, k).font = Font(bold=True)
        ws.cell(r, 2, v)
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 70

    # Sheet2 条款索引
    ws2 = wb.create_sheet("条款索引")
    clauses: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for d in details:
        cid = str(d.get("clause_id", "-"))
        if cid not in clauses:
            clauses[cid] = {
                "title": d.get("clause_title") or d.get("title", ""),
                "sev": d.get("severity", ""),
                "count": 0,
            }
            order.append(cid)
        clauses[cid]["count"] += 1
    ws2.append(["条款编号", "标题", "最高严重度", "出现次数"])
    for cid in sorted(order):
        c = clauses[cid]
        ws2.append([cid, c["title"], c["sev"], c["count"]])
    for cell in ws2[1]:
        cell.fill, cell.font, cell.alignment = head_fill, head_font, center
    for w, col in zip((16, 50, 12, 10), "ABCD"):
        ws2.column_dimensions[col].width = w
    for r in range(2, ws2.max_row + 1):
        sv = str(ws2.cell(r, 3).value or "")
        if sv in _SEV_FILL:
            ws2.cell(r, 3).fill = PatternFill("solid", start_color=_SEV_FILL[sv])
            ws2.cell(r, 3).font = Font(color="FFFFFF")

    # Sheet3 违规明细
    ws3 = wb.create_sheet("违规明细")
    ws3.append(["条款编号", "标题", "严重度", "状态", "实体ID", "实体类型", "当前值", "要求值", "偏差", "置信度", "说明"])
    for d in details:
        ws3.append([
            d.get("clause_id", ""), d.get("title", ""), d.get("severity", ""),
            d.get("status", ""), d.get("entity_id", ""), d.get("entity_type", ""),
            str(d.get("current_value", "")), str(d.get("required_value", "")),
            str(d.get("delta", "")), str(d.get("confidence", "")),
            d.get("explanation", d.get("description", "")),
        ])
    for cell in ws3[1]:
        cell.fill, cell.font, cell.alignment = head_fill, head_font, center
    widths = (12, 30, 10, 8, 16, 12, 10, 10, 10, 8, 50)
    for w, col in zip(widths, "ABCDEFGHIJK"):
        ws3.column_dimensions[col].width = w
    ws3.freeze_panes = "A2"

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()
