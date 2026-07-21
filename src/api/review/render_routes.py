"""
审查模块 — Render Routes
"""

from fastapi import Depends, HTTPException, Query, File, UploadFile, Request, Response
from . import (
    _get_dp,
    _get_sa,
    _get_fr,
    _get_sr,
    _get_aa,
    _get_pool,
    _get_rq,
    _get_pc,
    _get_rc,
    _get_rc_max,
    make_cache_key,
    router,
)
from . import (
    verify_api_key,
    SUPPORTED_FORMATS,
    MAX_FILE_SIZE,
    MAX_FILE_SIZE_MB,
    generate_file_id,
    store_file,
    get_file_path,
    MODELS_DIR,
)
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import uuid
import time
import asyncio
import json
import hashlib
from collections import Counter


@router.get("/review/queue/{task_id}")  # function call
async def review_queue_status(  # code
    task_id: str,  # 操作
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """查询审查任务排队状态

    返回指定 task_id 的排队位置、进度和状态。
    如果任务不存在，返回 404。
    """
    status = _get_rq().get_status(task_id)  # function call
    if status is None:  # check: value is None
        raise HTTPException(  # 抛出异常
            status_code=404,  # assignment
            detail={
                "status": "error",
                "error_code": "TASK_NOT_FOUND",
                "message": f"任务不存在: {task_id}",
            },  # 操作
        )  # code
    return status  # return


@router.get("/review/queue/stats")  # function call
async def review_queue_stats(  # code
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """查询审查任务队列统计信息"""
    return _get_rq().stats()  # return


@router.get("/render/{file_id}")  # function call
async def render_drawing(  # code
    file_id: str,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """将 DXF/DWG 图纸渲染为 SVG 供前端展示

    从存储的 DWG/DXF 文件中提取图元，生成缩放适配的 SVG 预览图。
    支持 LINE、LWPOLYLINE、CIRCLE、TEXT/MTEXT 等图元类型。
    最多渲染 2000 个图元以避免超时。
    """
    file_path = get_file_path(file_id)  # function call
    if not file_path:  # check: negated condition
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "error_code": "FILE_NOT_FOUND", "message": "文件不存在"},
        )  # 抛出异常

    import ezdxf  # import
    from io import StringIO  # import

    # 异常保护：捕获可能失败的调用
    try:  # 尝试
        doc = ezdxf.readfile(str(file_path))  # function call
        msp = doc.modelspace()  # function call
    except Exception:  # 捕获异常
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "error_code": "PARSE_FAILED", "message": "无法解析图纸文件"},
        )  # 抛出异常

    # ── 计算图元边界（用于 SVG viewBox 适配） ────────────────
    all_x, all_y = [], []  # assignment
    for entity in msp:  # 循环
        try:  # 尝试
            if entity.dxftype() == "LINE":  # condition: entity.dxftype() == "LINE":
                s, e = entity.dxf.start, entity.dxf.end  # assignment
                all_x.extend([s[0], e[0]])  # extend list
                all_y.extend([s[1], e[1]])  # extend list
            elif entity.dxftype() == "LWPOLYLINE":  # 分支
                pts = [(v[0], v[1]) for v in entity.get_points()]  # function call
                all_x.extend(p[0] for p in pts)  # extend list
                all_y.extend(p[1] for p in pts)  # extend list
            elif entity.dxftype() == "CIRCLE":  # 分支
                cx, cy = entity.dxf.center[:2]  # assignment
                r = entity.dxf.radius  # assignment
                all_x.extend([cx - r, cx + r])  # extend list
                all_y.extend([cy - r, cy + r])  # extend list
            elif entity.dxftype() in ("TEXT", "MTEXT"):  # 分支
                ins = entity.dxf.insert[:2]  # assignment
                all_x.append(ins[0])  # append to list
                all_y.append(ins[1])  # append to list
        except Exception:  # 捕获异常
            continue  # 继续循环

    # 根据条件判断分支：if not all_x
    if not all_x:  # check: negated condition
        return {"status": "error", "message": "图纸无有效图元"}  # return: dict

    # ── 计算 SVG viewBox 参数 ────────────────────────────────
    margin = 5.0  # assignment
    x_min, x_max = min(all_x) - margin, max(all_x) + margin  # 解包
    y_min, y_max = min(all_y) - margin, max(all_y) + margin  # 解包
    w, h = x_max - x_min, y_max - y_min  # assignment

    svg_w = min(max(w * 0.5, 400), 1200)  # SVG 输出宽度
    svg_h = min(max(h * 0.5, 300), 800)  # SVG 输出高度

    # ── 构建 SVG 字符串 ──────────────────────────────────────
    buf = StringIO()  # function call
    buf.write(
        f'<svg xmlns="http://www.w3.org/2000/svg" '  # assignment
        f'viewBox="{x_min} {-y_max} {w} {h}" '  # 操作
        f'width="{svg_w}" height="{svg_h}" '  # 操作
        f'style="background:#fff">\n'
    )  # assignment

    max_entities = 2000  # 渲染上限，避免大图纸超时
    drawn = 0  # assignment

    # 遍历处理
    for entity in msp:  # 循环
        if drawn >= max_entities:  # check: numeric comparison
            break  # 跳出循环
        dxftype = entity.dxftype()  # function call
        try:  # 尝试
            if dxftype == "LINE":  # condition: dxftype == "LINE":
                s, e = entity.dxf.start, entity.dxf.end  # assignment
                buf.write(
                    f'<line x1="{s[0]:.2f}" y1="{-s[1]:.2f}" '  # assignment
                    f'x2="{e[0]:.2f}" y2="{-e[1]:.2f}" '  # 操作
                    f'stroke="#333" stroke-width="0.5" />\n'
                )  # assignment
                drawn += 1  # accumulate
            elif dxftype == "LWPOLYLINE":  # 分支
                pts = [(v[0], -v[1]) for v in entity.get_points()]  # function call
                d = "M" + " L".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts)  # function call
                buf.write(
                    f'<path d="{d}" fill="none" stroke="#333" stroke-width="0.5" />\n'
                )  # function call
                drawn += 1  # accumulate
            elif dxftype == "CIRCLE":  # 分支
                cx, cy = entity.dxf.center[:2]  # assignment
                r = entity.dxf.radius  # assignment
                buf.write(
                    f'<circle cx="{cx:.2f}" cy="{-cy:.2f}" r="{r:.2f}" '  # assignment
                    f'fill="none" stroke="#333" stroke-width="0.5" />\n'
                )  # assignment
                drawn += 1  # accumulate
            elif dxftype in ("TEXT", "MTEXT"):  # 分支
                ins = entity.dxf.insert[:2]  # assignment
                txt = entity.dxf.text if hasattr(entity.dxf, "text") else ""  # attribute check
                ht = entity.dxf.height if hasattr(entity.dxf, "height") else 2.5  # attribute check
                buf.write(
                    f'<text x="{ins[0]:.2f}" y="{-ins[1]:.2f}" '  # assignment
                    f'font-size="{ht}" fill="#666">{txt[:30]}</text>\n'
                )  # assignment
                drawn += 1  # accumulate
        except Exception:  # 捕获异常
            continue  # 继续循环

    buf.write("</svg>")  # function call
    svg_content = buf.getvalue()  # function call

    return Response(content=svg_content, media_type="image/svg+xml")  # return


# ── 图纸渲染叠加层（违规高亮） ──────────────────────────


@router.get("/render/{file_id}/overlay")  # function call
async def render_drawing_overlay(  # code
    file_id: str,  # code
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """将 DXF/DWG 图纸渲染为 SVG，并叠加违规高亮标注

    在基础 SVG 渲染之上，通过 query params 传入违规位置信息进行高亮：
    - violations: JSON 编码的违规列表，每个含 entity_type, x, y, severity
    - 高亮颜色：critical=红色, major=橙色, normal=黄色
    """
    file_path = get_file_path(file_id)  # function call
    if not file_path:  # check: negated condition
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "error_code": "FILE_NOT_FOUND", "message": "文件不存在"},
        )  # 抛出异常

    import ezdxf  # import
    from io import StringIO  # import

    # 解析违规参数
    violations_param = request.query_params.get("violations", "") if request else ""
    try:  # 尝试
        violations = json.loads(violations_param) if violations_param else []
    except (json.JSONDecodeError, TypeError):  # 捕获异常
        violations = []  # assignment

    try:  # 尝试
        doc = ezdxf.readfile(str(file_path))  # function call
        msp = doc.modelspace()  # function call
    except Exception:  # 捕获异常
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "error_code": "PARSE_FAILED", "message": "无法解析图纸文件"},
        )  # 抛出异常

    # 计算边界
    all_x, all_y = [], []  # assignment
    for entity in msp:  # 循环
        try:  # 尝试
            if entity.dxftype() == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                all_x.extend([s[0], e[0]])
                all_y.extend([s[1], e[1]])
            elif entity.dxftype() == "LWPOLYLINE":
                pts = [(v[0], v[1]) for v in entity.get_points()]
                all_x.extend(p[0] for p in pts)
                all_y.extend(p[1] for p in pts)
            elif entity.dxftype() == "CIRCLE":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                all_x.extend([cx - r, cx + r])
                all_y.extend([cy - r, cy + r])
            elif entity.dxftype() in ("TEXT", "MTEXT"):
                ins = entity.dxf.insert[:2]
                all_x.append(ins[0])
                all_y.append(ins[1])
        except Exception:
            continue

    if not all_x:
        return {"status": "error", "message": "图纸无有效图元"}

    margin = 5.0
    x_min, x_max = min(all_x) - margin, max(all_x) + margin
    y_min, y_max = min(all_y) - margin, max(all_y) + margin
    w, h = x_max - x_min, y_max - y_min

    svg_w = min(max(w * 0.5, 400), 1200)
    svg_h = min(max(h * 0.5, 300), 800)

    buf = StringIO()
    buf.write(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{x_min} {-y_max} {w} {h}" '
        f'width="{svg_w}" height="{svg_h}" '
        f'style="background:#fff">\n'
    )

    max_entities = 2000
    drawn = 0

    # ── 绘制图元（基础渲染，同 render_drawing） ────────────
    for entity in msp:
        if drawn >= max_entities:
            break
        dxftype = entity.dxftype()
        try:
            if dxftype == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                buf.write(
                    f'<line x1="{s[0]:.2f}" y1="{-s[1]:.2f}" '
                    f'x2="{e[0]:.2f}" y2="{-e[1]:.2f}" '
                    f'stroke="#333" stroke-width="0.5" />\n'
                )
                drawn += 1
            elif dxftype == "LWPOLYLINE":
                pts = [(v[0], -v[1]) for v in entity.get_points()]
                d = "M" + " L".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts)
                buf.write(f'<path d="{d}" fill="none" stroke="#333" stroke-width="0.5" />\n')
                drawn += 1
            elif dxftype == "CIRCLE":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                buf.write(
                    f'<circle cx="{cx:.2f}" cy="{-cy:.2f}" r="{r:.2f}" '
                    f'fill="none" stroke="#333" stroke-width="0.5" />\n'
                )
                drawn += 1
            elif dxftype in ("TEXT", "MTEXT"):
                ins = entity.dxf.insert[:2]
                txt = entity.dxf.text if hasattr(entity.dxf, "text") else ""
                ht = entity.dxf.height if hasattr(entity.dxf, "height") else 2.5
                buf.write(
                    f'<text x="{ins[0]:.2f}" y="{-ins[1]:.2f}" '
                    f'font-size="{ht}" fill="#666">{txt[:30]}</text>\n'
                )
                drawn += 1
        except Exception:
            continue

    # ── 叠加违规高亮标注 ──────────────────────────────────
    severity_colors = {
        "critical": "#ef4444",
        "major": "#f97316",
        "normal": "#eab308",
        "minor": "#eab308",
    }
    severity_labels = {
        "critical": "严重",
        "major": "主要",
        "normal": "一般",
        "minor": "轻微",
    }

    for v in violations:  # 循环
        vtype = v.get("entity_type", "unknown")  # function call
        x = v.get("x", 0)  # function call
        y = v.get("y", 0)  # function call
        sev = v.get("severity", "major")  # function call
        clause = v.get("clause_id", "")  # function call
        color = severity_colors.get(sev, "#f97316")  # function call
        label = severity_labels.get(sev, "主要")  # function call

        # 高亮圆点
        buf.write(
            f'<circle cx="{x:.2f}" cy="{-y:.2f}" r="8" '
            f'fill="{color}" fill-opacity="0.3" '
            f'stroke="{color}" stroke-width="2" />\n'
        )
        # 标注文字
        buf.write(
            f'<text x="{x:.2f}" y="{-y - 10:.2f}" '
            f'fill="{color}" font-size="3" font-weight="bold" '
            f'text-anchor="middle">[{label}] {vtype}</text>\n'
        )
        if clause:  # check: truthy
            buf.write(
                f'<text x="{x:.2f}" y="{-y + 14:.2f}" '
                f'fill="{color}" font-size="2.5" '
                f'text-anchor="middle">{clause}</text>\n'
            )

    buf.write("</svg>")
    svg_content = buf.getvalue()

    return Response(content=svg_content, media_type="image/svg+xml")  # return


# ── PDF 审查报告导出 ─────────────────────────────────


@router.get("/review/{file_id}/pdf")  # function call
async def review_pdf(  # code
    file_id: str,  # code
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """导出审查报告 PDF

    对已审查过的图纸生成结构化 PDF 审查报告，包含封面、
    违规分类统计、每条违规详情及修正建议。
    """
    from src.baa_engine.report_generator import ReviewReport  # import

    # 获取文件路径
    file_path = get_file_path(file_id)  # function call
    if not file_path:  # check: negated condition
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "error_code": "FILE_NOT_FOUND", "message": "文件不存在"},
        )  # function call

    # 重新审查（保证使用最新引擎版本）
    import asyncio  # stdlib: async

    loop = asyncio.get_event_loop()  # function call

    result = await loop.run_in_executor(  # assignment
        _get_pool(), _get_dp().parse, str(file_path), file_id  # function call
    )  # code
    if not result.success:  # check: negated condition
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "PARSE_FAILED",
                "message": f"图纸解析失败: {result.error}",
            },
        )  # function call

    semantic = await loop.run_in_executor(  # assignment
        _get_pool(),  # code
        lambda: _get_sa().analyze(
            result.primitives, result.dimensions, dxf_path=str(file_path)
        ),  # function call
    )  # code
    entities = semantic["entities"]  # assignment

    from src.baa_engine.spec_repository import SpecRepository  # import
    from collections import Counter  # stdlib: collections

    repo = SpecRepository()  # function call
    details = []  # assignment
    registry_funcs = _get_fr().list_all()  # check all true

    start = time.time()  # get current time

    # ── 逐实体逐函数规范判定 ──────────────────────────────
    for e in entities:  # loop: iterate
        for func in registry_funcs:  # loop: iterate
            threshold_val, unit, op = repo.get_threshold(func.clause_id, "civil")  # function call
            try:  # try block
                r = _get_fr().execute_with_timeout(func, e)  # function call
                if r is None:  # check: value is None
                    continue  # code
                clause = {  # assignment
                    "standard": "GB50016",  # code
                    "clause_id": func.clause_id,  # code
                    "title": func.name,  # code
                    "text": func.description,  # code
                    "category": func.category.value,  # code
                }  # code
                f = _get_aa().build_finding(r, clause, {}, entities[:5])  # function call
                if f.judgement["result"] != "PASS":  # condition: f.judgement["result"] != "PASS":
                    details.append(
                        {  # code
                            "entity_id": e.get("id", ""),  # function call
                            "entity_type": e.get("type", ""),  # function call
                            "clause_id": f.clause.get("clause_id", ""),  # function call
                            "clause_title": f.clause.get("title", ""),  # function call
                            "func_id": func.func_id,  # code
                            "result": f.judgement["result"],  # code
                            "extracted_value": r.actual,  # code
                            "required_value": threshold_val,  # code
                            "difference": (r.actual or 0) - threshold_val,  # function call
                            "explanation": f.explanation[:120],  # code
                            "confidence": r.confidence,  # code
                        }
                    )  # code
            except Exception:  # catch exception
                continue  # code

    # ── 缺失检查 ──────────────────────────────────────────
    # 仅当函数的目标实体类型与图纸实体类型有交集时才执行缺失检查
    entity_types_in_drawing = set(e.get("type", "") for e in entities)
    for func in registry_funcs:  # loop: iterate
        if func.category.value != "exist":  # check: OR condition
            continue  # code
        # 跳过：目标实体类型与图纸实体类型无交集
        func_targets = set(func.target_entities) if func.target_entities else set()
        if func_targets and not func_targets.intersection(entity_types_in_drawing):
            continue
        has_match = any(func.matches(e) for e in entities)  # check any true
        if not has_match:  # check: negated condition
            r = _get_fr().execute_with_timeout(func, None)  # function call
            if r is not None and r.result != "PASS":  # check: value is not None
                clause = {  # assignment
                    "standard": "GB50016",  # code
                    "clause_id": func.clause_id,  # code
                    "title": func.name,  # code
                    "text": func.description,  # code
                    "category": func.category.value,  # code
                }  # code
                f = _get_aa().build_finding(r, clause, {}, entities[:5])  # function call
                details.append(
                    {  # code
                        "entity_id": "",  # code
                        "entity_type": "missing",  # code
                        "clause_id": f.clause.get("clause_id", ""),  # function call
                        "clause_title": f.clause.get("title", ""),  # function call
                        "func_id": func.func_id,  # code
                        "result": f.judgement["result"],  # code
                        "extracted_value": 0.0,  # code
                        "required_value": f.extracted_params.get(
                            "required_value", 1.0
                        ),  # function call
                        "difference": -f.extracted_params.get(
                            "required_value", 1.0
                        ),  # function call
                        "explanation": f.explanation[:120],  # code
                        "severity": "critical",  # code
                        "confidence": r.confidence,  # code
                    }
                )  # code

    elapsed = int((time.time() - start) * 1000)  # get current time
    entity_types = Counter(e["type"] for e in entities)  # function call
    violation_count = Counter(d["clause_id"] for d in details)  # function call

    summary = {  # assignment
        "total_entities": len(entities),  # get length
        "entity_types": dict(entity_types),  # function call
        "total_checks": len(entities) * len(registry_funcs),  # get length
        "violations": len(details),  # get length
        "violation_by_clause": dict(violation_count.most_common(10)),  # function call
        "building_type": "civil",  # code
        "processing_time_ms": elapsed,  # code
    }  # code

    # ── 修正建议 ──────────────────────────────────────────
    corrections = []  # assignment
    try:  # try block
        from src.baa_engine.correction_engine import CorrectionEngine  # import

        correction_engine = CorrectionEngine()  # function call
        review_result = {  # assignment
            "findings": [
                {  # code
                    "entity_id": d["entity_id"],  # code
                    "entity_type": d["entity_type"],  # code
                    "clause_id": d["clause_id"],  # code
                    "clause_title": d["clause_title"],  # code
                    "extracted_value": d["extracted_value"],  # code
                    "required_value": d["required_value"],  # code
                    "difference": d["difference"],  # code
                }
                for d in details
            ]  # code
        }  # code
        corrections = correction_engine.generate_for_result(review_result)  # function call
    except Exception:  # catch exception
        pass  # code

    # ── 生成 PDF ──────────────────────────────────────────
    generator = ReviewReport()  # function call
    pdf_bytes = generator.generate(  # assignment
        filename=file_path.name,  # assignment
        summary=summary,  # assignment
        details=details,  # assignment
        corrections=corrections,  # assignment
    )  # code

    return Response(  # return
        content=pdf_bytes,  # assignment
        media_type="application/pdf",  # assignment
        headers={  # assignment
            "Content-Disposition": f'attachment; filename="{file_path.stem}_report.pdf"',  # assignment
            "Content-Length": str(len(pdf_bytes)),  # get length
        },  # code
    )  # code


# ── 静态文件服务（模型下载） ─────────────────────────────


@router.get("/review/project/summary")
async def project_summary(
    file_ids: List[str] = Query(..., description="待汇总的文件ID列表（已审查过的文件）"),
    api_key: str = Depends(verify_api_key),
):
    """项目级审查汇总

    对已审查过的多个图纸文件生成跨文件的统一汇总报告，
    包含项目总体评分、合规率、严重级别分布、规范条目热力图、
    项目级风险识别等维度。

    不重新审查，从缓存读取各文件审查结果后聚合。
    """
    from src.baa_engine.project_summary import (
        aggregate_project_summary,
        format_project_report,
    )

    if not file_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_INPUT",
                "message": "file_ids 不能为空",
            },
        )
    if len(file_ids) > 50:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "TOO_MANY_FILES",
                "message": "单次最多汇总50个文件",
            },
        )

    # ── 从缓存读取各文件审查结果 ───────────────────────────
    file_results = []
    for file_id in file_ids:
        # 先尝试从 PersistentCache 读取
        from src.baa_engine.cache import get_cache as _get_cache

        cached = _get_cache().get(f"project_summary:{file_id}", "review_result")
        if cached and isinstance(cached, dict):
            file_results.append(cached)
            continue

        # 回退：尝试读取 drawing_parser 缓存中的审查结果
        # 如果缓存未命中，该文件不计入汇总
        file_results.append(
            {
                "filename": file_id,
                "status": "missing",
                "message": f"文件 {file_id} 的审查结果未缓存",
            }
        )

    # ── 聚合汇总 ──────────────────────────────────────────
    summary = aggregate_project_summary(file_results)
    report_text = format_project_report(summary)

    return {
        "status": "success",
        "summary": summary,
        "report_text": report_text,
    }
