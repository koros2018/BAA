"""D3-T2 Word 整改通知单 + 复查意见生成器（python-docx）。

生成原生 .docx 格式，客户可在线编辑/批注。
整改通知单：封面 + 按 function_id 分组整改清单 + 签字页
复查意见：封面 + 整改项 vs 复查结果对照表 + 签字页
"""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from ..report_generator.template import get_template_registry, ReportTemplate


def _rgb(hex_color: str) -> RGBColor:
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _set_cn_font(run, name: str = "宋体", size_pt: int = 9, bold: bool = False, color: Optional[RGBColor] = None) -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    if color:
        run.font.color.rgb = color


def _add_page_break(doc: Document) -> None:
    doc.add_page_break()


def _add_title(doc: Document, text: str, subtitle: str, template: ReportTemplate) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    _set_cn_font(run, name="黑体", size_pt=28, bold=True, color=_rgb(template.primary_color))
    doc.add_paragraph()  # spacing
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run2 = p2.add_run(subtitle)
    _set_cn_font(run2, name="黑体", size_pt=12, color=RGBColor(0x8C, 0x8C, 0x94))
    doc.add_paragraph()
    doc.add_paragraph()


def _add_info_row(doc: Document, label: str, value: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    run_label = p.add_run(f"{label}：")
    _set_cn_font(run_label, size_pt=11, bold=True)
    run_val = p.add_run(value)
    _set_cn_font(run_val, size_pt=11)


def _group_by_func(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        fid = it.get("function_id", "UNKNOWN") or "UNKNOWN"
        groups.setdefault(fid, []).append(it)
    return groups


def build_correction_notice_docx(
    items: List[Dict[str, Any]],
    review_meta: Dict[str, Any],
    output_path: Optional[str] = None,
    template_code: str = "national",
) -> str:
    """生成整改通知单 .docx。

    Args:
        items: get_confirmed_items() 返回的列表，每条含 id/review_id/function_id/entity_id/status/note/reason
        review_meta: {project_name, client, drawing_name, reviewer, corrector, deadline}
        output_path: 输出路径（缺省临时文件）
        template_code: D3-T1 模板配色
    Returns:
        输出 .docx 文件路径
    """
    template = get_template_registry().get(template_code)
    doc = Document()

    # ── 封面 ──
    _add_title(doc, "整改通知单", "CORRECTION NOTICE", template)
    notice_id = review_meta.get("notice_id", f"CN-{uuid.uuid4().hex[:8].upper()}")
    _add_info_row(doc, "编号", notice_id)
    _add_info_row(doc, "项目名称", review_meta.get("project_name", "未指定"))
    _add_info_row(doc, "图纸名称", review_meta.get("drawing_name", "未指定"))
    _add_info_row(doc, "审查人", review_meta.get("reviewer", "系统"))
    _add_info_row(doc, "整改期限", review_meta.get("deadline", "—"))
    _add_info_row(doc, "生成日期", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    doc.add_paragraph()

    # 统计
    by_func = _group_by_func(items)
    entities = {it.get("entity_id", "") for it in items if it.get("entity_id")}
    stats = doc.add_paragraph()
    stats.paragraph_format.space_before = Pt(12)
    stats.paragraph_format.space_after = Pt(12)
    _set_cn_font(stats.add_run("确认违规："), size_pt=10, bold=True)
    _set_cn_font(stats.add_run(f"{len(items)} 条"), size_pt=10)
    _set_cn_font(stats.add_run("    涉及条款："), size_pt=10, bold=True)
    _set_cn_font(stats.add_run(f"{len(by_func)} 条"), size_pt=10)
    _set_cn_font(stats.add_run("    涉及图元："), size_pt=10, bold=True)
    _set_cn_font(stats.add_run(f"{len(entities)} 个"), size_pt=10)

    doc.add_paragraph()
    p = doc.add_paragraph()
    _set_cn_font(p.add_run("说明："), size_pt=9, bold=True)
    _set_cn_font(p.add_run("本通知单列出了经审查确认后需要整改的违规条目。请项目负责人按照规范要求完成整改，并在复查栏签署意见。"), size_pt=9)

    _add_page_break(doc)

    # ── 整改清单（按 function_id 分组） ──
    seq = 0
    for fid in sorted(by_func.keys()):
        entries = by_func[fid]
        seq += 1
        sec_p = doc.add_paragraph()
        sec_p.paragraph_format.space_before = Pt(14)
        _set_cn_font(sec_p.add_run(f"第 {seq} 项：{fid} ({len(entries)} 处)"), size_pt=11, bold=True, color=_rgb(template.primary_color))

        table = doc.add_table(rows=1, cols=4)
        table.style = "Light Grid Accent 1"
        hdr = table.rows[0].cells
        for i, t in enumerate(["序号", "图元 ID", "批注", "整改要求"]):
            _set_cn_font(hdr[i].paragraphs[0].add_run(t), size_pt=9, bold=True)
            hdr[i].width = Cm([1.2, 4.5, 5.5, 5.5][i])
        for i, it in enumerate(entries):
            row = table.add_row().cells
            vals = [str(i + 1), str(it.get("entity_id", "—")), str(it.get("note", "—")), f"按 {fid} 要求整改"]
            for j, v in enumerate(vals):
                _set_cn_font(row[j].paragraphs[0].add_run(v), size_pt=9)
                row[j].width = Cm([1.2, 4.5, 5.5, 5.5][j])

        # 复查栏
        doc.add_paragraph()
        p = doc.add_paragraph()
        _set_cn_font(p.add_run("复查："), size_pt=9, bold=True)
        doc.add_paragraph()
        p = doc.add_paragraph()
        _set_cn_font(p.add_run("签字：___________    日期：___________"), size_pt=9)
        doc.add_paragraph()

    _add_page_break(doc)

    # ── 签字页 ──
    doc.add_paragraph()
    p = doc.add_paragraph()
    _set_cn_font(p.add_run("项目负责人确认"), size_pt=16, bold=True, color=_rgb(template.primary_color))
    doc.add_paragraph()
    p = doc.add_paragraph()
    _set_cn_font(p.add_run("本人已确认上述整改内容，将按要求完成整改。"), size_pt=9)
    doc.add_paragraph()
    doc.add_paragraph()
    p = doc.add_paragraph()
    _set_cn_font(p.add_run("签字：_____________________"), size_pt=9)
    doc.add_paragraph()
    p = doc.add_paragraph()
    _set_cn_font(p.add_run("日期：_____________________"), size_pt=9)
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_cn_font(p.add_run("BAA 合规审查系统自动生成 · 请打印后签署"), size_pt=8, color=RGBColor(0x8C, 0x8C, 0x94))

    out = Path(output_path or f"correction_notice_{notice_id}.docx")
    doc.save(str(out))
    return str(out)


def build_recheck_opinion_docx(
    rechecks: List[Dict[str, Any]],
    review_meta: Dict[str, Any],
    output_path: Optional[str] = None,
    template_code: str = "national",
) -> str:
    """生成复查意见 .docx。

    Args:
        rechecks: [{item_id, function_id, entity_id, status, opinion}]，status ∈ {passed, failed, pending}
        review_meta: {project_name, drawing_name, reviewer, corrector}
        output_path: 输出路径（缺省临时文件）
        template_code: D3-T1 模板配色
    Returns:
        输出 .docx 文件路径
    """
    template = get_template_registry().get(template_code)
    doc = Document()

    _add_title(doc, "复查意见", "RECHECK OPINION", template)
    recheck_id = review_meta.get("recheck_id", f"RO-{uuid.uuid4().hex[:8].upper()}")
    _add_info_row(doc, "编号", recheck_id)
    _add_info_row(doc, "项目名称", review_meta.get("project_name", "未指定"))
    _add_info_row(doc, "图纸名称", review_meta.get("drawing_name", "未指定"))
    _add_info_row(doc, "复查人", review_meta.get("reviewer", "系统"))
    _add_info_row(doc, "整改人", review_meta.get("corrector", "—"))
    _add_info_row(doc, "复查日期", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    doc.add_paragraph()

    _add_page_break(doc)

    # ── 对照表 ──
    table = doc.add_table(rows=1, cols=5)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    widths = [1.2, 3.0, 4.0, 2.0, 6.0]
    for i, t in enumerate(["序号", "整改项", "图元 ID", "复查状态", "复查意见"]):
        _set_cn_font(hdr[i].paragraphs[0].add_run(t), size_pt=9, bold=True)
        hdr[i].width = Cm(widths[i])

    status_map = {"passed": "通过", "failed": "不通过", "pending": "待补"}
    for i, it in enumerate(rechecks):
        row = table.add_row().cells
        vals = [
            str(i + 1),
            str(it.get("function_id", "—")),
            str(it.get("entity_id", "—")),
            status_map.get(it.get("status", ""), it.get("status", "—")),
            str(it.get("opinion", "—")),
        ]
        for j, v in enumerate(vals):
            _set_cn_font(row[j].paragraphs[0].add_run(v), size_pt=9)
            row[j].width = Cm(widths[j])

    _add_page_break(doc)

    # ── 签字页 ──
    doc.add_paragraph()
    p = doc.add_paragraph()
    _set_cn_font(p.add_run("复查人确认"), size_pt=16, bold=True, color=_rgb(template.primary_color))
    doc.add_paragraph()
    p = doc.add_paragraph()
    _set_cn_font(p.add_run("本人已复查上述整改内容，意见如上表所示。"), size_pt=9)
    doc.add_paragraph()
    doc.add_paragraph()
    p = doc.add_paragraph()
    _set_cn_font(p.add_run("签字：_____________________"), size_pt=9)
    doc.add_paragraph()
    p = doc.add_paragraph()
    _set_cn_font(p.add_run("日期：_____________________"), size_pt=9)
    doc.add_paragraph()
    doc.add_paragraph()
    p = doc.add_paragraph()
    _set_cn_font(p.add_run("整改人确认"), size_pt=16, bold=True, color=_rgb(template.primary_color))
    doc.add_paragraph()
    p = doc.add_paragraph()
    _set_cn_font(p.add_run("本人已确认复查结果，将按要求继续整改。"), size_pt=9)
    doc.add_paragraph()
    doc.add_paragraph()
    p = doc.add_paragraph()
    _set_cn_font(p.add_run("签字：_____________________"), size_pt=9)
    doc.add_paragraph()
    p = doc.add_paragraph()
    _set_cn_font(p.add_run("日期：_____________________"), size_pt=9)
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_cn_font(p.add_run("BAA 合规审查系统自动生成"), size_pt=8, color=RGBColor(0x8C, 0x8C, 0x94))

    out = Path(output_path or f"recheck_opinion_{recheck_id}.docx")
    doc.save(str(out))
    return str(out)
