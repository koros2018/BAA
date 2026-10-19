# -*- coding: utf-8 -*-
"""审查报告 HTML 导出（Roadmap v4 T-B4）：与 PDF 同结构（封面信息/评分/条款索引/结论/签署）。

自包含单文件（内联 CSS，无外部依赖），条款索引锚点可跳转（#clause-<id>）。
"""

from html import escape
from typing import Any, Dict, List

_SEV_COLOR = {
    "critical": "#c0392b",
    "major": "#d35400",
    "minor": "#27ae60",
}


def _sev_badge(sev: str) -> str:
    color = _SEV_COLOR.get(sev, "#7f8c8d")
    return (
        f'<span style="background:{color};color:#fff;padding:1px 8px;'
        f'border-radius:10px;font-size:12px">{escape(sev or "-")}</span>'
    )


def build_review_html(
    review_id: str,
    filename: str,
    summary: Dict[str, Any],
    details: List[Dict[str, Any]],
) -> str:
    total = len(details)
    sev: Dict[str, int] = {}
    for d in details:
        s = str(d.get("severity", "unknown"))
        sev[s] = sev.get(s, 0) + 1
    critical = sev.get("critical", 0)

    if total == 0:
        verdict = "经审查，未发现违反现行规范条款的情形，图纸审查通过。"
    elif critical == 0:
        verdict = f"经审查，发现 {total} 项提示类问题（无强制性条款违规），建议按提示逐项复核后通过。"
    else:
        verdict = (
            f"经审查，发现 {total} 项违规（其中强制性 {critical} 项），"
            "本图当前状态不符合审查通过条件，须完成整改并复核后重新提交。"
        )

    # 条款索引
    clauses: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for d in details:
        cid = str(d.get("clause_id", "-"))
        if cid not in clauses:
            clauses[cid] = {"title": d.get("clause_title") or d.get("title", ""), "count": 0, "sev": d.get("severity", "")}
            order.append(cid)
        clauses[cid]["count"] += 1
    toc_rows = "".join(
        f'<tr><td><a href="#clause-{escape(cid)}" style="color:#1a3a6b">{escape(cid)}</a></td>'
        f'<td>{escape(str(clauses[cid]["title"])[:40])}</td>'
        f'<td>{_sev_badge(str(clauses[cid]["sev"]))}</td><td>{clauses[cid]["count"]}</td></tr>'
        for cid in sorted(order)
    ) or '<tr><td colspan="4">无违规条款</td></tr>'

    # 违规明细（含锚点）
    detail_rows = "".join(
        f'<tr id="clause-{escape(str(d.get("clause_id", "")))}-{i}">'
        f"<td>{escape(str(d.get('clause_id', '')))}</td>"
        f"<td>{escape(str(d.get('title', '')))}</td>"
        f"<td>{_sev_badge(str(d.get('severity', '')))}</td>"
        f"<td>{escape(str(d.get('entity_type', '')))}</td>"
        f"<td>{escape(str(d.get('explanation', d.get('description', '')))[:80])}</td></tr>"
        for i, d in enumerate(details)
    ) or '<tr><td colspan="5">无违规记录</td></tr>'

    sev_cells = "".join(f"<td>{sev.get(k, 0)}</td>" for k in ("critical", "major", "minor"))
    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>审查报告 - {escape(filename)}</title>
<style>
body{{font-family:"Microsoft YaHei","PingFang SC",sans-serif;margin:0;color:#222}}
.hero{{background:linear-gradient(135deg,#1a3a6b,#2e5fa3);color:#fff;padding:36px 48px}}
.hero h1{{margin:0 0 6px;font-size:24px}} .hero .meta{{opacity:.85;font-size:13px}}
section{{padding:20px 48px}} h2{{color:#1a3a6b;border-left:4px solid #2e5fa3;padding-left:10px;font-size:18px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{border:1px solid #c8d2e0;padding:6px 8px;text-align:left}}
th{{background:#1a3a6b;color:#fff}}
tr:nth-child(even){{background:#f2f5fa}}
.verdict{{background:#eef2f8;border-left:4px solid #2e5fa3;padding:14px 18px;font-size:15px}}
.sign td{{height:42px}} .footer{{color:#888;font-size:12px;padding:16px 48px}}
</style></head><body>
<div class="hero"><h1>建筑图纸合规审查报告</h1>
<div class="meta">文件：{escape(filename)} ｜ 审查引擎：Blueprint AI Agent ｜ 报告 ID：{escape(review_id)} ｜ 违规 {total} 项（critical {critical}）</div></div>
<section><h2>条款索引</h2><table><tr><th>条款编号</th><th>标题</th><th>严重度</th><th>出现次数</th></tr>{toc_rows}</table></section>
<section><h2>审查结论</h2><div class="verdict">{escape(verdict)}</div>
<table style="margin-top:12px"><tr><th>critical</th><th>major</th><th>minor</th><th>合计</th></tr>
<tr>{sev_cells}<td>{total}</td></tr></table></section>
<section><h2>违规明细</h2><table><tr><th>条款</th><th>标题</th><th>严重度</th><th>实体类型</th><th>说明</th></tr>{detail_rows}</table></section>
<section><h2>签署与归档</h2>
<table class="sign"><tr><th>角色</th><th>签名</th><th>日期</th></tr>
<tr><td>编制（审查引擎）</td><td></td><td></td></tr>
<tr><td>审核</td><td></td><td></td></tr>
<tr><td>批准</td><td></td><td></td></tr></table></section>
<div class="footer">免责声明：本报告由 AI 审查引擎自动生成，供设计校核参考，不替代法定施工图审查机构出具的审查意见。</div>
</body></html>"""
