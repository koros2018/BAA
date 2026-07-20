"""
审查模块 — Review Routes
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
    task_obj, task_id, queue_position = await _get_rq().wait_and_dequeue(file_id)
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
        func_ids = [f.func_id for f in registry_funcs]
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
                            "result": f.judgement["result"],
                            "extracted_value": f.extracted_params["extracted_value"],
                            "required_value": f.extracted_params.get("required_value", 1.2),
                            "difference": f.extracted_params.get("difference", 0),
                            "explanation": f.explanation[:120],
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
                            "result": f.judgement["result"],
                            "extracted_value": 0.0,
                            "required_value": f.extracted_params.get("required_value", 1.0),
                            "difference": -f.extracted_params.get("required_value", 1.0),
                            "explanation": f.explanation[:120],
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
        },  # code
        "details": details[:100],  # 最多返回100条详情
        "file_id": file_id,  # 字段
        "building_type": building_type,  # 字段
        "standard": standard,  # code
        "processing_time_ms": elapsed,  # 字段
    }  # code

    # ── 生成修正建议（支持规则/LLM/混合模式） ──────────────
    try:
        correction_mode = query_params.get(
            "correction_mode", os.environ.get("BAA_CORRECTION_MODE", "hybrid")
        )

        # 构建 findings 列表（与 correction_engine 兼容）
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

    # 审查任务队列排队
    task_obj, task_id, queue_position = await _get_rq().wait_and_dequeue("from-data")
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
                for func in registry_funcs:
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
                                "result": f.judgement["result"],
                                "extracted_value": f.extracted_params["extracted_value"],
                                "required_value": f.extracted_params.get("required_value", 1.2),
                                "difference": f.extracted_params.get("difference", 0),
                                "severity": f.judgement.get("severity", "major"),
                                "explanation": f.explanation[:120],
                            }
                        )

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
                                "result": f.judgement["result"],
                                "severity": "critical",
                                "extracted_value": 0.0,
                                "required_value": f.extracted_params.get("required_value", 1.0),
                                "difference": -f.extracted_params.get("required_value", 1.0),
                                "explanation": f.explanation[:120],
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

        response_data = {  # assignment
            "status": "success",  # 字段
            "summary": {  # 字段
                "total_entities": len(entities),  # 字段
                "entity_types": dict(entity_types),  # 字段
                "total_checks": len(entities) * len(registry_funcs),  # 字段
                "violations": len(details),  # 字段
                "violation_by_clause": dict(violation_count.most_common(10)),  # 字段
            },  # code
            "details": details[:100],  # 字段
            "building_type": building_type,  # 字段
            "processing_time_ms": elapsed,  # 字段
        }  # code

        # ── 生成修正建议（支持规则/LLM/混合模式） ──────────────
        try:
            correction_mode = request_params.get(
                "correction_mode", os.environ.get("BAA_CORRECTION_MODE", "hybrid")
            )

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
