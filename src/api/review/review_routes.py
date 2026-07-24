"""
审查模块 — Review Routes
"""

from fastapi import Depends, HTTPException, Query, File, UploadFile, Request, Response
from enum import Enum


class ConfidenceTier(str, Enum):
    """置信度语义分级（P61）"""

    CONFIRMED = "confirmed"  # ≥0.85，确认违规
    SUSPECTED = "suspected"  # 0.60~0.85，疑似违规
    NEEDS_REVIEW = "needs_review"  # <0.60，建议人工复核


def _confidence_tier(confidence: float) -> str:
    """将 0~1 置信度映射为语义分级标签。"""
    if confidence >= 0.85:
        return ConfidenceTier.CONFIRMED.value
    if confidence >= 0.60:
        return ConfidenceTier.SUSPECTED.value
    return ConfidenceTier.NEEDS_REVIEW.value


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

# ── P62: 结构化摘要 ────────────────────────────────────────

COMPLIANCE_GUIDE = {
    "critical": "必须整改，否则无法通过施工图审查，建议优先处理",
    "major": "建议整改，影响建筑性能或施工便利性",
    "minor": "可选择性优化，提升图纸质量",
}

COMPLIANCE_PATHS = {
    "dim": "按规范限值调整构件尺寸（宽度/高度/净距）",
    "exist": "补充缺失的消防/疏散设施实体",
    "dist": "调整构件间距以满足最小安全距离",
    "count": "增加设施数量满足最低配置要求",
    "area": "优化平面布局以满足面积/分区要求",
    "attr": "修正构件属性（材料/等级/标识）",
    "light": "补充/调整照明设施以满足照度要求",
    "vac": "优化疏散路径，确保连通性",
}


def _classify_priority(d: dict) -> str:
    """P62: severity + confidence → 整改优先级 P0/P1/P2。

    P0 = 高置信度 + critical，立即整改
    P1 = 高置信度 + major 或 中置信度 + critical，尽快整改
    P2 = 其余，计划性优化
    """
    sev = d.get("severity", "minor")
    tier = d.get("confidence_tier", "")
    if tier == "confirmed" and sev == "critical":
        return "P0"
    if (tier == "confirmed" and sev == "major") or (tier == "suspected" and sev == "critical"):
        return "P1"
    return "P2"


def _derive_compliance_path(d: dict) -> str:
    """P62: 从 func_id/clause_id 推导整改路径指引。"""
    fid = (d.get("func_id") or d.get("clause_id") or "").lower()
    for prefix, guide in COMPLIANCE_PATHS.items():
        if prefix in fid:
            return guide
    return "参照对应规范条款，逐项整改"


def _build_structured_summary(details: list[dict]) -> dict:
    """P62: 从 details 生成结构化摘要。

    返回:
    - top_violations: TOP-5 违规，按优先级 + 置信度排序
    - priority_distribution: P0/P1/P2 计数
    - category_distribution: 按 category 分组
    - compliance_actions: 整改路径指引（按优先级聚合）
    """
    if not details:
        return {
            "top_violations": [],
            "priority_distribution": {"P0": 0, "P1": 0, "P2": 0},
            "category_distribution": {},
            "compliance_actions": [],
        }

    annotated = []
    for d in details:
        annotated.append(
            {
                **d,
                "priority": _classify_priority(d),
                "compliance_path": _derive_compliance_path(d),
            }
        )

    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    annotated.sort(
        key=lambda x: (priority_order.get(x["priority"], 9), -(x.get("confidence", 0.5)))
    )

    top_violations = annotated[:5]
    top_violations_out = []
    for i, v in enumerate(top_violations, 1):
        top_violations_out.append(
            {
                "rank": i,
                "priority": v["priority"],
                "severity": v.get("severity", "minor"),
                "confidence": v.get("confidence", 0.5),
                "confidence_tier": v.get("confidence_tier", ""),
                "clause_id": v.get("clause_id", ""),
                "clause_title": v.get("clause_title", ""),
                "func_id": v.get("func_id", ""),
                "explanation": v.get("explanation", ""),
                "compliance_path": v["compliance_path"],
            }
        )

    priority_distribution = {"P0": 0, "P1": 0, "P2": 0}
    for a in annotated:
        p = a["priority"]
        priority_distribution[p] = priority_distribution.get(p, 0) + 1

    category_distribution = {}
    for a in annotated:
        cat = a.get("category", "other")
        if cat not in category_distribution:
            category_distribution[cat] = {"count": 0, "P0": 0, "P1": 0, "P2": 0}
        category_distribution[cat]["count"] += 1
        category_distribution[cat][a["priority"]] += 1

    compliance_actions = []
    for p_label in ("P0", "P1", "P2"):
        matched = [a for a in annotated if a["priority"] == p_label]
        if not matched:
            continue
        paths = set(a["compliance_path"] for a in matched)
        compliance_actions.append(
            {
                "priority": p_label,
                "priority_label": {"P0": "立即整改", "P1": "尽快整改", "P2": "计划优化"}[p_label],
                "count": len(matched),
                "description": COMPLIANCE_GUIDE.get(
                    matched[0].get("severity", "minor"), "参照规范整改"
                ),
                "action_paths": list(paths),
            }
        )

    return {
        "top_violations": top_violations_out,
        "priority_distribution": priority_distribution,
        "category_distribution": category_distribution,
        "compliance_actions": compliance_actions,
    }


# ── End P62 ────────────────────────────────────────────────


@router.post("/review")  # function call
async def review(  # code
    file: UploadFile = File(...),  # function call
    full: bool = Query(False, description="返回完整图元列表"),  # function call
    building_type: str = Query(
        "civil", description="建筑类型: civil(民用) / industrial(工业)"
    ),  # function call
    building_types: Optional[List[str]] = Query(
        None, description="多建筑类型列表（混合建筑场景）"
    ),  # function call
    standard: str = Query(
        "GB 50016-2014", description="规范标准: GB 50016-2014 / NFPA 101-2021 / NFPA 5000-2021"
    ),  # function call
    webhook_url: Optional[str] = Query(
        None, description="P71: 审查完成后 POST 到此 URL"
    ),  # function call
    webhook_type: str = Query(
        "generic", description="P71: generic | feishu | dingtalk"
    ),  # function call
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """图纸合规审查（免费试用）

    对上传的 DWG/DXF 图纸进行完整合规审查，返回：
    - 审查摘要（实体统计、检查项数、违规分布）
    - 违规详情（每条违规的 clause_id、提取值、要求值、差值）
    - 修正建议（基于 correction_engine 生成）

    支持多标准：
    - GB 50016-2014（中国建筑防火规范，默认）
    - NFPA 101-2021（美国生命安全规范）
    - NFPA 5000-2021（美国建筑规范）

    与 /deconstruct 的区别：
    - /deconstruct 侧重"拆解"，输出结构化实体数据
    - /review 侧重"审查"，输出合规报告和修正建议
    """
    # ── 检查文件格式 ────────────────────────────────────────
    filename = file.filename or "unknown"  # assignment
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""  # function call

    if ext not in SUPPORTED_FORMATS:  # check: membership test
        raise HTTPException(  # 抛出异常
            status_code=400,  # assignment
            detail={  # assignment
                "status": "error",  # 字段
                "error_code": "UNSUPPORTED_FORMAT",  # 字段
                "message": f"不支持的文件格式: {ext}",  # 字段
            },  # code
        )  # code

    # ── 检查文件大小 ────────────────────────────────────────
    content = await file.read()  # function call
    if len(content) > MAX_FILE_SIZE:  # check: numeric comparison
        raise HTTPException(  # 抛出异常
            status_code=400,  # assignment
            detail={  # assignment
                "status": "error",  # 字段
                "error_code": "FILE_TOO_LARGE",  # 字段
                "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",  # 字段
            },  # code
        )  # code

    # ── 存储文件到磁盘 ──────────────────────────────────────
    file_id = generate_file_id()  # function call
    file_path = store_file(content, file_id, ext)  # function call

    # ── 缓存检查：相同文件内容+参数秒级返回 ──────────────────
    file_hash = hashlib.sha256(content).hexdigest()[:32]  # function call
    cache_key = make_cache_key(file_hash, standard, building_type)  # function call
    # 先查内存缓存（最快）
    cached = _get_rc().get(cache_key)  # function call
    if cached is not None:  # check: value is not None
        cached["file_id"] = file_id  # assignment
        return cached  # return
    # 再查持久化缓存（服务重启后恢复）
    persistent = _get_pc().get(cache_key, "review_result")  # function call
    if persistent is not None:  # check: value is not None
        _get_rc()[cache_key] = persistent  # assignment
        persistent["file_id"] = file_id  # assignment
        return persistent  # return

    start = time.time()  # get current time
    loop = asyncio.get_event_loop()  # function call

    # 并发控制：审查任务队列排队
    task_obj, task_id, queue_position = await _get_rq().wait_and_dequeue(
        file_id, webhook_url=webhook_url, webhook_type=webhook_type
    )
    if task_obj is None:
        return {
            "status": "error",
            "error_code": "QUEUE_TIMEOUT",
            "message": "排队超时（超过300秒），请稍后重试",
            "file_id": file_id,
        }

    try:
        # Step 1: 图纸解析（CPU密集型 → 线程池）
        _get_rq().update_progress(task_id, 10.0)
        result = await loop.run_in_executor(  # assignment
            _get_pool(), _get_dp().parse, str(file_path), file_id  # 操作
        )  # code
        if not result.success:  # check: negated condition
            _get_rq().fail(task_id, result.error)
            return {  # return: dict
                "status": "error",  # 字段
                "error_code": "PARSE_FAILED",  # 字段
                "message": f"图纸解析失败: {result.error}",  # 字段
                "file_id": file_id,  # 字段
                "queue_info": {"task_id": task_id},
            }  # code

        # Step 2: 语义分析（CPU密集型 → 线程池）
        _get_rq().update_progress(task_id, 50.0)
        semantic = await loop.run_in_executor(  # assignment
            _get_pool(),  # 解包
            lambda: _get_sa().analyze(  # 操作
                result.primitives,
                result.dimensions,  # 解包
                building_type=building_type,  # assignment
            ),  # code
        )  # code
        entities = semantic["entities"]  # assignment
        _get_rq().update_progress(task_id, 70.0)

    except Exception as e:
        _get_rq().fail(task_id, str(e))
        raise

    # 多建筑类型：向后兼容，building_types 为空时使用 building_type
    # （有效类型在 _do_clustering 中从 _effective_types 读取）
    # Step 3: 规范判定（CPU 密集型，移至线程池避免阻塞事件循环）
    # 250 原子函数 × N 实体的链式判定放在 run_in_executor，
    # 避免 gunicorn worker 因 120s timeout 被 SIGKILL。
    _effective_types = building_types if building_types else [building_type]

    def _do_clustering(entities):
        """在线程池中执行规范判定 + 缺失检查"""
        from src.baa_engine.spec_repository import SpecRepository
        from collections import Counter

        repo = SpecRepository()
        clause_results = Counter()
        details = []
        registry_funcs = _get_fr().list_all()

        def get_strict_threshold(clause_id: str) -> tuple:
            worst_val, worst_unit, worst_op = None, None, None
            for bt in _effective_types:
                v, u, o = repo.get_threshold(clause_id, bt)
                if worst_val is None or v > worst_val:
                    worst_val, worst_unit, worst_op = v, u, o
            return worst_val, worst_unit, worst_op

        # 链式依赖执行
        func_ids = [f.func_id for f in registry_funcs if not getattr(f, 'requires_global_context', False)]
        global_funcs = [f for f in registry_funcs if getattr(f, 'requires_global_context', False)]  # 需要全局上下文的函数
        for e in entities:
            chained_results = _get_fr().execute_chained(func_ids, e)
            for fid, r in chained_results.items():
                func = _get_fr().get(fid)
                if func is None:
                    continue
                threshold_val, unit, op = get_strict_threshold(func.clause_id)
                if r is None:
                    continue
                clause_results[func.clause_id] += 1
                if r.result != "PASS":
                    clause = {
                        "standard": "GB50016",
                        "clause_id": func.clause_id,
                        "title": func.name,
                        "text": func.description,
                        "category": func.category.value,
                    }
                    f = _get_aa().build_finding(r, clause, e, entities[:5])
                    details.append(
                        {
                            "entity_id": e.get("id", e.get("type", "")),
                            "entity_type": e["type"],
                            "clause_id": f.clause.get("clause_id", ""),
                            "clause_title": f.clause.get("title", ""),
                            "func_id": func.func_id,
                            "result": f.judgement["result"],
                            "extracted_value": f.extracted_params["extracted_value"],
                            "required_value": f.extracted_params.get("required_value", 1.2),
                            "difference": f.extracted_params.get("difference", 0),
                            "severity": f.judgement.get(
                                "severity", "major"
                            ),  # P62: 透传 severity 供优先级判定
                            "explanation": f.explanation[:120],
                            "confidence": r.confidence,
                            "confidence_tier": _confidence_tier(r.confidence),
                        }
                    )

        # ── P70: requires_global_context 函数全局聚合判定 ──
        # 这些函数需要按全局/防火分区聚合统计，而不是逐实体判定
        # 例如 EXIST-083/093（每个防火分区应设≥2个消防救援窗）
        # 之前的逻辑对每个 window 实体单独判定，导致 count=1 < 2 全部 FAIL
        for func in global_funcs:
            if func.category.value != "exist":
                continue
            func_targets = set(func.target_entities) if func.target_entities else set()
            matching = [e for e in entities if e.get("type", "") in func_targets]
            if not matching:
                # 无匹配实体 → 缺失检查
                r = _get_fr().execute_with_timeout(func, None)
                if r is not None and r.result != "PASS":
                    clause = {
                        "standard": "GB50016",
                        "clause_id": func.clause_id,
                        "title": func.name,
                        "text": func.description,
                        "category": func.category.value,
                    }
                    details.append(
                        {
                            "entity_id": "",
                            "entity_type": "missing",
                            "clause_id": func.clause_id,
                            "clause_title": func.name,
                            "func_id": func.func_id,
                            "result": "FAIL",
                            "extracted_value": 0.0,
                            "required_value": func.threshold,
                            "difference": -func.threshold,
                            "explanation": f"未检出{func.name}所需实体类型: {', '.join(func_targets)}",
                            "severity": "critical",
                            "confidence": 1.0,
                            "confidence_tier": "confirmed",
                        }
                    )
            else:
                # 有匹配实体 → 按全局计数判定
                count = len(matching)
                clause_results[func.clause_id] += 1
                if count < func.threshold:
                    details.append(
                        {
                            "entity_id": "",
                            "entity_type": ",".join(func_targets),
                            "clause_id": func.clause_id,
                            "clause_title": func.name,
                            "func_id": func.func_id,
                            "result": "FAIL",
                            "extracted_value": float(count),
                            "required_value": float(func.threshold),
                            "difference": float(count - func.threshold),
                            "explanation": f"全局共检出{count}个，要求≥{func.threshold}",
                            "severity": "critical",
                            "confidence": 1.0,
                            "confidence_tier": "confirmed",
                        }
                    )

        # 缺失检查：对 EXIST-* 函数检查是否有匹配实体
        # 仅当函数的目标实体类型与图纸实体类型有交集时才执行缺失检查
        # 如果图纸类型完全不包含该函数关心的实体类型（如泵房图纸不含汽车库），跳过
        entity_types_in_drawing = set(e.get("type", "") for e in entities)
        for func in registry_funcs:
            if func.category.value != "exist":
                continue
            # 跳过：目标实体类型与图纸实体类型无交集
            func_targets = set(func.target_entities) if func.target_entities else set()
            if func_targets and not func_targets.intersection(entity_types_in_drawing):
                continue
            has_match = any(func.matches(e) for e in entities)
            if not has_match:
                r = _get_fr().execute_with_timeout(func, None)
                if r is not None and r.result != "PASS":
                    clause = {
                        "standard": "GB50016",
                        "clause_id": func.clause_id,
                        "title": func.name,
                        "text": func.description,
                        "category": func.category.value,
                    }
                    f = _get_aa().build_finding(r, clause, {}, entities[:5])
                    details.append(
                        {
                            "entity_id": "",
                            "entity_type": "missing",
                            "clause_id": f.clause.get("clause_id", ""),
                            "clause_title": f.clause.get("title", ""),
                            "func_id": func.func_id,
                            "result": f.judgement["result"],
                            "extracted_value": 0.0,
                            "required_value": f.extracted_params.get("required_value", 1.0),
                            "difference": -f.extracted_params.get("required_value", 1.0),
                            "explanation": f.explanation[:120],
                            "severity": "critical",
                            "confidence": r.confidence,
                            "confidence_tier": _confidence_tier(r.confidence),
                        }
                    )

        return clause_results, details

    try:
        clause_results, details = await loop.run_in_executor(_get_pool(), _do_clustering, entities)
    except Exception as e:
        _get_rq().fail(task_id, str(e))
        raise

    elapsed = int((time.time() - start) * 1000)  # get current time

    # ── 统计 ─────────────────────────────────────────────────
    entity_types = Counter(e["type"] for e in entities)  # 各类型实体数量
    violation_count = Counter(d["clause_id"] for d in details)  # 各规范条款违规数

    # ── 计算综合评分（P36） ────────────────────────────────
    total_score = 100.0  # assignment
    if len(entities) > 0 and len(details) > 0:  # check: numeric comparison
        violation_deduction = len(details) * 5.0  # get length
        critical_count = sum(1 for d in details if d.get("severity") == "critical")  # aggregate sum
        major_count = sum(1 for d in details if d.get("severity") == "major")  # aggregate sum
        total_score = max(
            0, 100.0 - violation_deduction - critical_count * 10 - major_count * 3
        )  # get maximum

    avg_confidence = 1.0  # assignment
    confidences = [d.get("confidence", 1.0) for d in details if "confidence" in d]  # function call
    if confidences:  # condition: confidences:
        avg_confidence = sum(confidences) / len(confidences)  # get length

    # ── 置信度分级统计（P61） ─────────────────────────────
    tier_counts = {"confirmed": 0, "suspected": 0, "needs_review": 0}
    for d in details:
        tier = d.get("confidence_tier", _confidence_tier(d.get("confidence", 1.0)))
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    # ── P62: 结构化摘要 ─────────────────────────────────
    structured_summary = _build_structured_summary(details)

    # 原子函数列表（_do_clustering 内部有局部定义，这里取一次用于响应）
    registry_funcs = _get_fr().list_all()

    response_data = {  # assignment
        "status": "success",  # 字段
        "summary": {  # 字段
            "total_entities": len(entities),  # 字段
            "entity_types": dict(entity_types),  # 字段
            "total_checks": len(entities) * len(registry_funcs),  # 字段
            "violations": len(details),  # 字段
            "violation_by_clause": dict(violation_count.most_common(10)),  # 字段
            "score": total_score,  # 字段
            "avg_confidence": round(avg_confidence, 2),  # 字段
            "confidence_tier_counts": tier_counts,  # P61: 置信度分级统计
        },  # code
        "structured_summary": structured_summary,  # P62
        "details": details[:100],  # 最多返回100条详情
        "file_id": file_id,  # 字段
        "building_type": building_type,  # 字段
        "standard": standard,  # code
        "processing_time_ms": elapsed,  # 字段
    }  # code

    # ── 生成修正建议（支持规则/LLM/混合模式） ──────────────
    try:
        correction_mode = os.environ.get("BAA_CORRECTION_MODE", "rule")

        # 构建 findings 列表（与 correction_engine 兼容）
        # func_id 是修正建议模板匹配的关键字段，必须透传
        review_result_for_correction = {
            "findings": [
                {
                    "entity_id": d["entity_id"],
                    "entity_type": d["entity_type"],
                    "clause_id": d["clause_id"],
                    "clause_title": d["clause_title"],
                    "func_id": d.get("func_id", ""),
                    "extracted_value": d["extracted_value"],
                    "required_value": d["required_value"],
                    "difference": d["difference"],
                }
                for d in details
            ]
        }

        # P65: 注入图纸上下文（entities），LLM 模式需要完整实体列表做空间分析
        review_result_for_correction["entities"] = entities  # operation

        if correction_mode == "rule":
            # 纯规则引擎模式
            from src.baa_engine.correction_engine import CorrectionEngine

            correction_engine = CorrectionEngine()
            corrections = correction_engine.generate_for_result(review_result_for_correction)
        else:
            # LLM 或混合模式
            from src.baa_engine.llm_correction import LLMCorrectionEngine

            llm_engine = LLMCorrectionEngine(mode=correction_mode)
            corrections = llm_engine.generate_for_result(review_result_for_correction)
        response_data["corrections"] = corrections  # 操作
    except Exception:  # 捕获异常
        response_data["corrections"] = []  # 操作

    # ── 如果请求 full 模式，返回完整图元列表 ─────────────────
    if full:  # condition: full:
        response_data["all_entities"] = [  # 操作
            {"id": e.get("id", e.get("type", "")), "type": e["type"], "bbox": e["bbox"]}  # 字面量
            for e in entities  # 循环
        ]  # code

    # ── 标记任务完成 ────────────────────────────────────────
    _get_rq().complete(task_id, response_data)
    response_data["queue_info"] = {
        "task_id": task_id,
        "queue_position": queue_position,
    }

    # ── 写入缓存（内存 + 持久化） ──────────────────────────
    if file_hash:  # condition: file_hash:
        cache_key = make_cache_key(file_hash, standard, building_type)  # function call
        if len(_get_rc()) >= _get_rc_max():  # check: numeric comparison
            old_key = next(iter(_get_rc()))  # function call
            del _get_rc()[old_key]  # code
        _get_rc()[cache_key] = response_data  # assignment
        # 异步写入持久化缓存（不阻塞响应）
        _get_pc().set(cache_key, response_data, "review_result")  # function call

    # ── 保存审查历史到数据库 ────────────────────────────────
    try:
        from .review_history import save_review_result

        review_id = file_id or task_id or str(uuid.uuid4())
        save_review_result(review_id, filename, response_data)
    except Exception:
        pass  # 保存失败不影响审查结果返回

    return response_data  # return


@router.get("/review/pdf", tags=["Review"])  # P69: PDF 报告导出
async def export_review_pdf(  # code
    review_id: str = Query(..., description="审查记录 ID"),  # assignment
    lang: str = Query("zh", description="报告语言: zh/cn/en"),  # assignment
    api_key: str = Depends(verify_api_key),  # assignment
):
    """导出审查结果为 PDF 报告

    基于审查记录 ID 生成完整 PDF 报告，包含：
    - 封面（项目信息、审查概要）
    - 合规度评分页
    - 违规分类统计
    - 违规详情（TOP-N）
    - 修正建议
    """
    from fastapi.responses import StreamingResponse
    from .review_history import get_review_detail

    detail = get_review_detail(review_id)
    if not detail:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "error_code": "REVIEW_NOT_FOUND",
                "message": f"审查记录 {review_id} 不存在",
            },
        )

    summary = detail.get("summary", {})
    details = detail.get("details", [])
    corrections = detail.get("corrections", [])
    filename = detail.get("drawingName", "review")

    structured_summary = _build_structured_summary(details)
    # P62: 结构化摘要注入 PDF
    try:
        from src.baa_engine.report_generator import ReviewReport

        reporter = ReviewReport()
        pdf_bytes = reporter.generate(
            filename=filename,
            summary=summary,
            details=details,
            corrections=corrections,
            structured_summary=structured_summary,
            lang=lang,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "error_code": "PDF_GENERATION_FAILED",
                "message": f"PDF 生成失败: {str(e)}",
            },
        )

    safe_name = filename.rsplit(".", 1)[0] if "." in filename else filename
    pdf_name = f"{safe_name}_BAA_报告.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pdf_name}"'},
    )


@router.post("/review-from-data")  # function call
async def review_from_data(  # code
    body: dict,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """从已解析的结构化数据执行规范审查（无需重新上传文件）

    接收前端或其他服务已解析好的实体数据，直接运行规范判定。
    适用于已有结构化数据的场景，跳过图纸解析步骤。
    """
    entities = body.get("entities", [])  # function call
    building_type = body.get("building_type", "civil")  # function call
    building_types = body.get("building_types")  # function call
    _effective_types_from_data = building_types if building_types else [building_type]  # 赋值

    start = time.time()  # get current time

    # 审查任务队列排队（P71: 支持 body 中的 webhook_url/webhook_type）
    _review_webhook_url = body.get("webhook_url")
    _review_webhook_type = body.get("webhook_type", "generic")
    task_obj, task_id, queue_position = await _get_rq().wait_and_dequeue(
        "from-data", webhook_url=_review_webhook_url, webhook_type=_review_webhook_type
    )
    if task_obj is None:
        return {
            "status": "error",
            "error_code": "QUEUE_TIMEOUT",
            "message": "排队超时，请稍后重试",
        }

    try:
        _get_rq().update_progress(task_id, 10.0)

        # ── 规范判定（CPU 密集型，移到线程池避免阻塞事件循环）
        # 250 原子函数 × N 实体的双循环在主事件循环跑会超过 gunicorn 120s timeout
        # 导致 SIGKILL → ERR_EMPTY_RESPONSE，参考 /review 端点的 _do_clustering 模式
        def _do_clustering_from_data(
            entities,
        ) -> tuple:  # function: def _do_clustering_from_data(entities) -> tuple:
            """在线程池中执行规范判定 + 缺失检查"""
            from src.baa_engine.spec_repository import SpecRepository
            from collections import Counter

            repo = SpecRepository()
            clause_results = Counter()
            details = []
            registry_funcs = _get_fr().list_all()
            global_funcs = [f for f in registry_funcs if getattr(f, 'requires_global_context', False)]  # P70

            def get_strict_threshold(
                clause_id: str,
            ) -> tuple:  # function: def get_strict_threshold(clause_id: str) -> tuple:
                worst_val, worst_unit, worst_op = None, None, None
                for bt in _effective_types_from_data:
                    v, u, o = repo.get_threshold(clause_id, bt)
                    if worst_val is None or v > worst_val:
                        worst_val, worst_unit, worst_op = v, u, o
                return worst_val, worst_unit, worst_op

            for e in entities:
                for func in [f for f in registry_funcs if not getattr(f, 'requires_global_context', False)]:
                    threshold_val, unit, op = get_strict_threshold(func.clause_id)
                    func.threshold = threshold_val
                    func.unit = unit
                    func.operator = op
                    r = _get_fr().execute_with_timeout(func, e)
                    if r is None:
                        continue
                    clause_results[func.clause_id] += 1
                    if r.result != "PASS":
                        clause = {
                            "standard": "GB50016",
                            "clause_id": func.clause_id,
                            "title": func.name,
                            "text": func.description,
                            "category": func.category.value,
                        }
                        f = _get_aa().build_finding(r, clause, e, entities[:5])
                        details.append(
                            {
                                "entity_id": e.get("id", e.get("type", "")),
                                "entity_type": e["type"],
                                "clause_id": f.clause.get("clause_id", ""),
                                "clause_title": f.clause.get("title", ""),
                                "func_id": func.func_id,
                                "result": f.judgement["result"],
                                "extracted_value": f.extracted_params["extracted_value"],
                                "required_value": f.extracted_params.get("required_value", 1.2),
                                "difference": f.extracted_params.get("difference", 0),
                                "severity": f.judgement.get("severity", "major"),
                                "explanation": f.explanation[:120],
                                "confidence": r.confidence,
                                "confidence_tier": _confidence_tier(r.confidence),
                            }
                        )

            # P70: requires_global_context 函数全局聚合判定
            for func in global_funcs:
                if func.category.value != "exist":
                    continue
                func_targets = set(func.target_entities) if func.target_entities else set()
                matching = [e for e in entities if e.get("type", "") in func_targets]
                if not matching:
                    r = _get_fr().execute_with_timeout(func, None)
                    if r is not None and r.result != "PASS":
                        details.append({
                            "entity_id": "",
                            "entity_type": "missing",
                            "clause_id": func.clause_id,
                            "clause_title": func.name,
                            "func_id": func.func_id,
                            "result": "FAIL",
                            "extracted_value": 0.0,
                            "required_value": func.threshold,
                            "difference": -func.threshold,
                            "explanation": f"未检出{func.name}所需实体类型: {', '.join(func_targets)}",
                            "severity": "critical",
                            "confidence": 1.0,
                            "confidence_tier": "confirmed",
                        })
                else:
                    count = len(matching)
                    clause_results[func.clause_id] += 1
                    if count < func.threshold:
                        details.append({
                            "entity_id": "",
                            "entity_type": ",".join(func_targets),
                            "clause_id": func.clause_id,
                            "clause_title": func.name,
                            "func_id": func.func_id,
                            "result": "FAIL",
                            "extracted_value": float(count),
                            "required_value": float(func.threshold),
                            "difference": float(count - func.threshold),
                            "explanation": f"全局共检出{count}个，要求≥{func.threshold}",
                            "severity": "critical",
                            "confidence": 1.0,
                            "confidence_tier": "confirmed",
                        })

            # 缺失检查
            # 仅当函数的目标实体类型与图纸实体类型有交集时才执行缺失检查
            entity_types_in_drawing = set(e.get("type", "") for e in entities)
            for func in registry_funcs:
                if func.category.value != "exist":
                    continue
                # 跳过：目标实体类型与图纸实体类型无交集
                func_targets = set(func.target_entities) if func.target_entities else set()
                if func_targets and not func_targets.intersection(entity_types_in_drawing):
                    continue
                has_match = any(func.matches(e) for e in entities)
                if not has_match:
                    r = _get_fr().execute_with_timeout(func, None)
                    if r is not None and r.result != "PASS":
                        clause = {
                            "standard": "GB50016",
                            "clause_id": func.clause_id,
                            "title": func.name,
                            "text": func.description,
                            "category": func.category.value,
                        }
                        f = _get_aa().build_finding(r, clause, {}, entities[:5])
                        details.append(
                            {
                                "entity_id": "",
                                "entity_type": "missing",
                                "clause_id": f.clause.get("clause_id", ""),
                                "clause_title": f.clause.get("title", ""),
                                "func_id": func.func_id,
                                "result": f.judgement["result"],
                                "severity": "critical",
                                "extracted_value": 0.0,
                                "required_value": f.extracted_params.get("required_value", 1.0),
                                "difference": -f.extracted_params.get("required_value", 1.0),
                                "explanation": f.explanation[:120],
                                "confidence": r.confidence,
                                "confidence_tier": _confidence_tier(r.confidence),
                            }
                        )

            return clause_results, details

        # 获取当前事件循环，必须在 run_in_executor 调用之前
        loop = asyncio.get_event_loop()
        registry_funcs = _get_fr().list_all()

        try:
            clause_results, details = await loop.run_in_executor(
                _get_pool(), _do_clustering_from_data, entities
            )
        except Exception as e:
            _get_rq().fail(task_id, str(e))
            raise

        # registry_funcs 在 _do_clustering_from_data 内部已重新 list_all，
        # 这里重新获取供后续 total_checks 统计使用
        registry_funcs = _get_fr().list_all()

        elapsed = int((time.time() - start) * 1000)  # get current time
        entity_types = Counter(e["type"] for e in entities)  # function call
        violation_count = Counter(d["clause_id"] for d in details)  # function call

        # ── 置信度分级统计（P61） ─────────────────────────────
        tier_counts = {"confirmed": 0, "suspected": 0, "needs_review": 0}
        confidences = [d.get("confidence", 1.0) for d in details]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 1.0
        for d in details:
            tier = d.get("confidence_tier", _confidence_tier(d.get("confidence", 1.0)))
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        response_data = {  # assignment
            "status": "success",  # 字段
            "summary": {  # 字段
                "total_entities": len(entities),  # 字段
                "entity_types": dict(entity_types),  # 字段
                "total_checks": len(entities) * len(registry_funcs),  # 字段
                "violations": len(details),  # 字段
                "violation_by_clause": dict(violation_count.most_common(10)),  # 字段
                "avg_confidence": round(avg_confidence, 2),  # P61
                "confidence_tier_counts": tier_counts,  # P61
            },  # code
            "details": details[:100],  # 字段
            "building_type": building_type,  # 字段
            "processing_time_ms": elapsed,  # 字段
        }  # code

        # ── 生成修正建议（支持规则/LLM/混合模式） ──────────────
        try:
            correction_mode = os.environ.get("BAA_CORRECTION_MODE", "rule")

            review_result_for_correction = {
                "findings": [
                    {
                        "entity_id": d["entity_id"],
                        "entity_type": d["entity_type"],
                        "clause_id": d["clause_id"],
                        "clause_title": d["clause_title"],
                        "extracted_value": d["extracted_value"],
                        "required_value": d["required_value"],
                        "difference": d["difference"],
                    }
                    for d in details
                ]
            }

            if correction_mode == "rule":
                from src.baa_engine.correction_engine import CorrectionEngine

                ce = CorrectionEngine()
                corrections = ce.generate_for_result(review_result_for_correction)
            else:
                from src.baa_engine.llm_correction import LLMCorrectionEngine

                llm_engine = LLMCorrectionEngine(mode=correction_mode)
                corrections = llm_engine.generate_for_result(review_result_for_correction)

            response_data["corrections"] = corrections
            response_data["raw_result"] = {
                "elements": [],
                "details": details,
                "corrections": corrections,
                "summary": response_data.get("summary", {}),
            }
        except Exception:
            response_data["corrections"] = []
            response_data["raw_result"] = {"elements": [], "details": details}  # 操作

    except Exception as outer_e:
        _get_rq().fail(task_id, str(outer_e))
        raise

    # 标记任务完成
    _get_rq().complete(task_id, response_data)
    response_data["queue_info"] = {
        "task_id": task_id,
        "queue_position": queue_position,
    }

    # ── 保存审查历史到数据库 ────────────────────────────────
    try:
        from .review_history import save_review_result

        review_id = task_id or str(uuid.uuid4())
        drawing_name = body.get("drawing_name", body.get("filename", "from-data"))
        save_review_result(review_id, drawing_name, response_data)
    except Exception:
        pass

    return response_data  # return


# ── P45 热工性能 K 值计算 ──────────────────────────────────

THERMAL_MATERIALS = {
    "rockwool": {"name": "岩棉板", "lambda": 0.035, "density": 800},
    "eps": {"name": "EPS聚苯板", "lambda": 0.040, "density": 20},
    "xps": {"name": "XPS挤塑板", "lambda": 0.030, "density": 35},
    "pu": {"name": "聚氨酯", "lambda": 0.024, "density": 40},
    "aerogel": {"name": "气凝胶", "lambda": 0.012, "density": 120},
}

THERMAL_THRESHOLDS = {
    "severe_cold": {
        "exterior_wall": 0.45,
        "roof": 0.35,
        "ground_floor": 0.30,
        "exterior_window": 2.0,
    },
    "cold": {"exterior_wall": 0.60, "roof": 0.50, "ground_floor": 0.45, "exterior_window": 2.4},
    "hot_cold": {"exterior_wall": 1.50, "roof": 1.20, "ground_floor": 0.60, "exterior_window": 3.2},
    "hot_warm": {"exterior_wall": 2.00, "roof": 1.50, "ground_floor": 0.80, "exterior_window": 4.0},
}

HI = 8.7  # 内表面传热系数 W/(m²·K)
HO = 23.0  # 外表面传热系数 W/(m²·K)


@router.post("/thermal/k-value")  # function call
async def compute_thermal_k(  # code
    body: dict,
):
    """P45 热工性能 K 值计算

    输入：构件类型(compType)、保温材料(material)、厚度(mm)、气候带(climate)
    返回：K值、阈值对比、建议厚度
    """
    comp_type = body.get("compType", "exterior_wall")
    material_key = body.get("material", "rockwool")
    thickness_mm = body.get("thicknessMm", 50)
    climate = body.get("climate", "severe_cold")

    if comp_type not in THERMAL_THRESHOLDS["severe_cold"]:
        comp_type = "exterior_wall"
    if material_key not in THERMAL_MATERIALS:
        material_key = "rockwool"
    if climate not in THERMAL_THRESHOLDS:
        climate = "severe_cold"
    if not isinstance(thickness_mm, (int, float)) or thickness_mm <= 0:
        thickness_mm = 50

    mat = THERMAL_MATERIALS[material_key]
    d_m = thickness_mm / 1000.0
    R = 1.0 / HI + d_m / mat["lambda"] + 1.0 / HO
    K = 1.0 / R
    threshold = THERMAL_THRESHOLDS[climate][comp_type]
    passed = K <= threshold

    result = {
        "status": "success",
        "K": round(K, 4),
        "R": round(R, 3),
        "threshold": threshold,
        "passed": passed,
        "compType": comp_type,
        "material": mat["name"],
        "lambda": mat["lambda"],
        "thicknessMm": thickness_mm,
        "climate": climate,
    }

    if not passed:
        # 反算当前材料满足要求所需的最小厚度
        R_needed = 1.0 / threshold
        d_needed_m = (R_needed - 1.0 / HI - 1.0 / HO) * mat["lambda"]
        d_needed_mm = max(0, d_needed_m * 1000)
        result["requiredThicknessMm"] = round(d_needed_mm, 1)
        result["additionalThicknessMm"] = round(max(0, d_needed_mm - thickness_mm), 1)

    return result


@router.post("/reconstruct")  # function call
async def reconstruct(  # code
    body: dict,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """BIM 重构（需授权验证）

    将已解析的审查结果重构为 IFC 格式的 BIM 模型文件。
    需要有效的 auth_token（通过支付获取）。
    """
    file_id = body.get("file_id", "")  # function call
    auth_token = body.get("auth_token", "")  # function call

    # ── 验证授权 ────────────────────────────────────────────
    auth_payload = verify_auth_token(auth_token)  # function call
    if auth_payload is None:  # check: value is None
        raise HTTPException(  # 抛出异常
            status_code=402,  # assignment
            detail={  # assignment
                "status": "error",  # 字段
                "error_code": "AUTH_FAILED",  # 字段
                "message": "支付授权验证失败，请确认订单已支付",  # 字段
            },  # code
        )  # code

    # ── 检查 file_id 是否存在 ───────────────────────────────
    file_path = get_file_path(file_id)  # function call
    if not file_path:  # check: negated condition
        raise HTTPException(  # 抛出异常
            status_code=404,  # assignment
            detail={  # assignment
                "status": "error",  # 字段
                "error_code": "FILE_NOT_FOUND",  # 字段
                "message": f"文件不存在: {file_id}",  # 字段
            },  # code
        )  # code

    # ── 执行重构（暂返回 mock 数据） ─────────────────────────
    order_id = f"baa-order-{uuid.uuid4().hex[:8]}"  # function call
    model_path = MODELS_DIR / order_id  # assignment
    model_path.mkdir(parents=True, exist_ok=True)  # function call
    (model_path / "model.ifc").write_text(  # 写入模型文件
        f"# Mock IFC file for order {order_id}\n"  # code
        f"# Generated from file: {file_id}\n"  # code
    )  # code

    base_url = str(app.root_path) if app.root_path else "http://localhost:8000"  # function call

    return {  # return: dict
        "status": "success",  # 字段
        "order_id": body.get("order_id", ""),  # 字段
        "baa_order_id": order_id,  # 字段
        "model_url": f"{base_url}/models/{order_id}/model.ifc",  # 字段
        "elements_count": 40,  # 字段
        "processing_time_ms": 15000,  # 字段
        "file_size_mb": 2.5,  # 字段
        "valid_until": (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z",  # 字段
    }  # code


@router.get("/order/{order_id}")  # function call
async def get_order(  # code
    order_id: str,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """订单状态查询

    查询 BIM 重构订单的处理状态和结果下载链接。
    """
    order_dir = MODELS_DIR / order_id  # assignment
    if not order_dir.exists():  # check: negated condition
        raise HTTPException(  # 抛出异常
            status_code=404,  # assignment
            detail={  # assignment
                "status": "error",  # 字段
                "error_code": "ORDER_NOT_FOUND",  # 字段
                "message": "订单不存在",  # 字段
            },  # code
        )  # code

    model_file = order_dir / "model.ifc"  # assignment
    if model_file.exists():  # condition: model_file.exists():
        return {  # return: dict
            "status": "completed",  # 字段
            "order_id": order_id,  # 字段
            "progress": 100,  # 字段
            "model_url": f"/models/{order_id}/model.ifc",  # 字段
            "file_size_mb": round(model_file.stat().st_size / 1024 / 1024, 2),  # 字段
        }  # code
    else:  # 否则
        return {  # return: dict
            "status": "processing",  # 字段
            "order_id": order_id,  # 字段
            "progress": 50,  # 字段
            "estimated_remaining_ms": 15000,  # 字段
        }  # code


# ── 图纸渲染 ──────────────────────────────────────────────
