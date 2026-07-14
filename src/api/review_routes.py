"""
审查模块路由（review/* + render/* + order + compare + project_summary）
从 baa_api.py 拆分，使用 APIRouter 注册
"""

from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from src.api.api_globals import *  # noqa: F401, F403
import hashlib
import os
from datetime import datetime
from typing import Optional, List, Dict
import uuid
import time
import asyncio
from pathlib import Path
import json
from collections import Counter

router = APIRouter()


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
    cached = _review_cache.get(cache_key)  # function call
    if cached is not None:  # check: value is not None
        cached["file_id"] = file_id  # assignment
        return cached  # return
    # 再查持久化缓存（服务重启后恢复）
    persistent = _persistent_cache.get(cache_key, "review_result")  # function call
    if persistent is not None:  # check: value is not None
        _review_cache[cache_key] = persistent  # assignment
        persistent["file_id"] = file_id  # assignment
        return persistent  # return

    start = time.time()  # get current time
    loop = asyncio.get_event_loop()  # function call

    # 并发控制：审查任务队列排队
    task_obj, task_id, queue_position = await _review_queue.wait_and_dequeue(file_id)
    if task_obj is None:
        return {
            "status": "error",
            "error_code": "QUEUE_TIMEOUT",
            "message": "排队超时（超过300秒），请稍后重试",
            "file_id": file_id,
        }

    try:
        # Step 1: 图纸解析（CPU密集型 → 线程池）
        _review_queue.update_progress(task_id, 10.0)
        result = await loop.run_in_executor(  # assignment
            ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id  # 操作
        )  # code
        if not result.success:  # check: negated condition
            _review_queue.fail(task_id, result.error)
            return {  # return: dict
                "status": "error",  # 字段
                "error_code": "PARSE_FAILED",  # 字段
                "message": f"图纸解析失败: {result.error}",  # 字段
                "file_id": file_id,  # 字段
                "queue_info": {"task_id": task_id},
            }  # code

        # Step 2: 语义分析（CPU密集型 → 线程池）
        _review_queue.update_progress(task_id, 50.0)
        semantic = await loop.run_in_executor(  # assignment
            ENGINE_THREAD_POOL,  # 解包
            lambda: _semantic_analyzer.analyze(  # 操作
                result.primitives,
                result.dimensions,  # 解包
                building_type=building_type,  # assignment
            ),  # code
        )  # code
        entities = semantic["entities"]  # assignment
        _review_queue.update_progress(task_id, 70.0)

    except Exception as e:
        _review_queue.fail(task_id, str(e))
        raise

    # 多建筑类型：向后兼容，building_types 为空时使用 building_type
    effective_types = building_types if building_types else [building_type]  # assignment

    # Step 3: 规范判定（使用 building_type 确定阈值）
    from src.baa_engine.spec_repository import SpecRepository  # import

    repo = SpecRepository()  # function call
    from collections import Counter  # stdlib: collections

    clause_results = Counter()  # function call
    details = []  # assignment
    registry_funcs = _func_registry.list_all()  # check all true

    # 收集已出现的实体类型
    found_entity_types = set(e["type"] for e in entities)  # function call

    # 多建筑类型并行匹配：取最严格阈值
    def get_strict_threshold(
        clause_id: str,
    ) -> tuple:  # function: def get_strict_threshold(clause_id: str) -> tuple:
        worst_val, worst_unit, worst_op = None, None, None  # assignment
        for bt in effective_types:  # loop: iterate
            v, u, o = repo.get_threshold(clause_id, bt)  # function call
            if worst_val is None or v > worst_val:  # check: value is None
                worst_val, worst_unit, worst_op = v, u, o  # assignment
        return worst_val, worst_unit, worst_op  # return

    # P32: 链式依赖执行 — 按依赖拓扑顺序，结果在函数间共享
    # 对每个实体，按依赖拓扑顺序执行所有原子函数
    func_ids = [f.func_id for f in registry_funcs]  # 提取所有函数ID
    for e in entities:  # 循环
        # 使用链式执行：依赖函数先执行，结果缓存后传递给后续函数
        chained_results = _func_registry.execute_chained(func_ids, e)  # function call
        for fid, r in chained_results.items():  # 循环
            func = _func_registry.get(fid)  # function call
            if func is None:  # condition: func is None:
                continue  # 跳过
            threshold_val, unit, op = get_strict_threshold(func.clause_id)  # function call
            # 使用链式执行结果，无需重复设置阈值（已在chained_results中）
            if r is None:  # check: value is None
                continue  # 继续循环
            clause_results[func.clause_id] += 1  # accumulate
            if r.result != "PASS":  # condition: r.result != "PASS":
                clause = {  # assignment
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # code
                f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])  # function call
                details.append(
                    {  # code
                        "entity_id": e.get("id", e.get("type", "")),  # 字段
                        "entity_type": e["type"],  # 字段
                        "clause_id": f.clause.get("clause_id", ""),  # 字段
                        "clause_title": f.clause.get("title", ""),  # 字段
                        "result": f.judgement["result"],  # 字段
                        "extracted_value": f.extracted_params["extracted_value"],  # 字段
                        "required_value": f.extracted_params.get("required_value", 1.2),  # 字段
                        "difference": f.extracted_params.get("difference", 0),  # 字段
                        "explanation": f.explanation[:120],  # 字段
                    }
                )  # code

    # 缺失检查：对 EXIST-* 函数检查是否有匹配实体
    for func in registry_funcs:  # 循环
        if func.category.value != "exist":  # check: OR condition
            continue  # 继续循环
        has_match = any(func.matches(e) for e in entities)  # check any true
        if not has_match:  # check: negated condition
            r = _func_registry.execute_with_timeout(func, None)  # 触发缺失检查模式
            if r is not None and r.result != "PASS":  # check: value is not None
                clause = {  # assignment
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # code
                f = _attribution_analyzer.build_finding(
                    r, clause, {}, entities[:5]
                )  # function call
                details.append(
                    {  # code
                        "entity_id": "",  # 字段
                        "entity_type": "missing",  # 字段
                        "clause_id": f.clause.get("clause_id", ""),  # 字段
                        "clause_title": f.clause.get("title", ""),  # 字段
                        "result": f.judgement["result"],  # 字段
                        "extracted_value": 0.0,  # 字段
                        "required_value": f.extracted_params.get("required_value", 1.0),  # 字段
                        "difference": -f.extracted_params.get("required_value", 1.0),  # 字段
                        "explanation": f.explanation[:120],  # 字段
                    }
                )  # code

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
    except Exception as e:  # 捕获异常
        response_data["corrections"] = []  # 操作

    # ── 如果请求 full 模式，返回完整图元列表 ─────────────────
    if full:  # condition: full:
        response_data["all_entities"] = [  # 操作
            {"id": e.get("id", e.get("type", "")), "type": e["type"], "bbox": e["bbox"]}  # 字面量
            for e in entities  # 循环
        ]  # code

    # ── 标记任务完成 ────────────────────────────────────────
    _review_queue.complete(task_id, response_data)
    response_data["queue_info"] = {
        "task_id": task_id,
        "queue_position": queue_position,
    }

    # ── 写入缓存（内存 + 持久化） ──────────────────────────
    if file_hash:  # condition: file_hash:
        cache_key = make_cache_key(file_hash, standard, building_type)  # function call
        if len(_review_cache) >= _REVIEW_CACHE_MAX:  # check: numeric comparison
            old_key = next(iter(_review_cache))  # function call
            del _review_cache[old_key]  # code
        _review_cache[cache_key] = response_data  # assignment
        # 异步写入持久化缓存（不阻塞响应）
        _persistent_cache.set(cache_key, response_data, "review_result")  # function call

    return response_data  # return


@router.get("/review/queue/{task_id}")  # function call
async def review_queue_status(  # code
    task_id: str,  # 操作
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """查询审查任务排队状态

    返回指定 task_id 的排队位置、进度和状态。
    如果任务不存在，返回 404。
    """
    status = _review_queue.get_status(task_id)  # function call
    if status is None:  # check: value is None
        raise HTTPException(  # 抛出异常
            status_code=404,  # assignment
            detail={"status": "error", "error_code": "TASK_NOT_FOUND", "message": f"任务不存在: {task_id}"},  # 操作
        )  # code
    return status  # return


@router.delete("/review/queue/{task_id}")  # function call
async def review_queue_cancel(  # code
    task_id: str,  # 操作
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """取消排队中的审查任务

    仅能取消排队中（status=queued）的任务。
    已在运行或已完成的任务无法取消。
    """
    cancelled = _review_queue.cancel(task_id)  # function call
    if not cancelled:  # check: negated condition
        status_info = _review_queue.get_status(task_id)  # function call
        if status_info is None:  # check: value is None
            raise HTTPException(  # 抛出异常
                status_code=404,  # assignment
                detail={"status": "error", "error_code": "TASK_NOT_FOUND", "message": f"任务不存在: {task_id}"},  # 操作
            )  # code
        raise HTTPException(  # 抛出异常
            status_code=409,  # assignment
            detail={
                "status": "error",
                "error_code": "TASK_CANT_CANCEL",
                "message": f"任务当前状态为 {status_info['status']}，无法取消",
            },  # 操作
        )  # code
    return {"status": "success", "message": f"任务 {task_id} 已取消"}  # return


@router.get("/review/queue/stats")  # function call
async def review_queue_stats(  # code
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """查询审查任务队列统计信息"""
    return _review_queue.stats()  # return


@router.post("/batch-review")  # function call
async def batch_review(  # code
    files: List[UploadFile] = File(...),  # 操作
    building_type: str = Query(
        "civil", description="建筑类型: civil(民用) / industrial(工业)"
    ),  # function call
    building_types: Optional[List[str]] = Query(
        None, description="多建筑类型列表（混合建筑场景）"
    ),  # function call
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """多文件批量审查

    同时审查最多 20 个图纸文件，返回每个文件的单独审查结果，
    以及跨文件的交叉分析（同一违规类别在多少文件中出现）。
    """
    if len(files) < 1:  # check: numeric comparison
        raise HTTPException(
            status_code=400, detail={"status": "error", "error_code": "NO_FILES", "message": "请至少上传一个文件"}
        )  # 抛出异常
    if len(files) > 20:  # check: numeric comparison
        raise HTTPException(
            status_code=400, detail={"status": "error", "error_code": "TOO_MANY_FILES", "message": "单次最多审查20个文件"}
        )  # 抛出异常

    start = time.time()  # get current time
    loop = asyncio.get_event_loop()  # function call
    from src.baa_engine.spec_repository import SpecRepository  # import
    from collections import Counter  # stdlib: collections

    repo = SpecRepository()  # function call
    registry_funcs = _func_registry.list_all()  # check all true

    results = []  # assignment
    all_details = []  # assignment
    all_entities = []  # assignment
    total_violations = 0  # assignment
    total_checks = 0  # assignment
    total_files = len(files)  # get length
    completed_files = 0  # assignment

    # ── 并发执行每个文件的审查（P37优化） ────────────────────
    async def _review_single_file(file: UploadFile) -> Dict:  # function call
        """单个文件审查（独立执行）"""
        nonlocal completed_files  # code

        # 使用审查任务队列排队
        temp_file_id = generate_file_id()
        task_obj, task_id, queue_position = await _review_queue.wait_and_dequeue(temp_file_id)
        if task_obj is None:
            completed_files += 1
            return {
                "filename": file.filename,
                "status": "error",
                "error_code": "QUEUE_TIMEOUT",
                "message": "排队超时，请稍后重试",
            }

        try:
            ext = (
                file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
            )  # function call
            if ext not in SUPPORTED_FORMATS:  # check: membership test
                completed_files += 1  # accumulate
                _review_queue.fail(task_id, f"不支持的文件格式: {ext}")
                return {  # return: dict
                    "filename": file.filename,  # code
                    "status": "error",  # code
                    "error_code": "UNSUPPORTED_FORMAT",  # code
                    "message": f"不支持的文件格式: {ext}",  # code
                }  # code

            content = await file.read()  # function call
            if len(content) > MAX_FILE_SIZE:  # check: numeric comparison
                completed_files += 1  # accumulate
                _review_queue.fail(task_id, "文件过大")
                return {  # return: dict
                    "filename": file.filename,  # code
                    "status": "error",  # code
                    "error_code": "FILE_TOO_LARGE",  # code
                    "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",  # get length
                }  # code

            file_id = generate_file_id()  # function call
            file_path = store_file(content, file_id, ext)  # function call

            # ── 解析（CPU密集型 → 线程池） ───────────────────
            _review_queue.update_progress(task_id, 10.0)
            result = await loop.run_in_executor(  # assignment
                ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id  # function call
            )  # code
            if not result.success:  # check: negated condition
                completed_files += 1  # accumulate
                _review_queue.fail(task_id, result.error)
                return {  # return: dict
                    "filename": file.filename,  # code
                    "status": "error",  # code
                    "error_code": "PARSE_FAILED",  # code
                    "message": f"图纸解析失败: {result.error}",  # code
                }  # code

            # ── 语义分析（CPU密集型 → 线程池） ───────────────
            _review_queue.update_progress(task_id, 50.0)
            semantic = await loop.run_in_executor(  # assignment
                ENGINE_THREAD_POOL,  # code
                lambda: _semantic_analyzer.analyze(  # code
                    result.primitives,
                    result.dimensions,  # code
                    building_type=building_type,  # assignment
                ),  # code
            )  # code
            entities = semantic["entities"]  # assignment
            _review_queue.update_progress(task_id, 70.0)

            # 多建筑类型
            effective_types = building_types if building_types else [building_type]  # assignment

            # ── 规范判定 ──────────────────────────────────────
            details = []  # assignment
            found_entity_types = set(e["type"] for e in entities)  # function call

            def get_strict_threshold(
                clause_id: str,
            ) -> tuple:  # function: def get_strict_threshold(clause_id: str) -> tuple:
                worst_val, worst_unit, worst_op = None, None, None  # assignment
                for bt in effective_types:  # loop: iterate
                    v, u, o = repo.get_threshold(clause_id, bt)  # function call
                    if worst_val is None or v > worst_val:  # check: value is None
                        worst_val, worst_unit, worst_op = v, u, o  # assignment
                return worst_val, worst_unit, worst_op  # return

            for e in entities:  # loop: iterate
                for func in registry_funcs:  # loop: iterate
                    threshold_val, unit, op = get_strict_threshold(func.clause_id)  # function call
                    func.threshold = threshold_val  # assignment
                    func.unit = unit  # assignment
                    func.operator = op  # assignment
                    r = _func_registry.execute_with_timeout(func, e)  # function call
                    if r is None:  # check: value is None
                        continue  # code
                    if r.result != "PASS":  # condition: r.result != "PASS":
                        clause = {  # assignment
                            "standard": "GB50016",  # code
                            "clause_id": func.clause_id,  # code
                            "title": func.name,  # code
                            "text": func.description,  # code
                            "category": func.category.value,  # code
                        }  # code
                        f = _attribution_analyzer.build_finding(
                            r, clause, e, entities[:5]
                        )  # function call
                        details.append(
                            {  # code
                                "entity_id": e.get("id", e.get("type", "")),  # function call
                                "entity_type": e["type"],  # code
                                "clause_id": f.clause.get("clause_id", ""),  # function call
                                "clause_title": f.clause.get("title", ""),  # function call
                                "result": f.judgement["result"],  # code
                                "extracted_value": f.extracted_params["extracted_value"],  # code
                                "required_value": f.extracted_params.get(
                                    "required_value", 1.2
                                ),  # function call
                                "difference": f.extracted_params.get(
                                    "difference", 0
                                ),  # function call
                                "explanation": f.explanation[:120],  # code
                                "confidence": r.confidence,  # code
                                "severity": r.severity.value,  # code
                            }
                        )  # code

            # ── 缺失检查 ──────────────────────────────────────
            for func in registry_funcs:  # loop: iterate
                if func.category.value != "exist":  # check: OR condition
                    continue  # code
                has_match = any(func.matches(e) for e in entities)  # check any true
                if not has_match:  # check: negated condition
                    r = _func_registry.execute_with_timeout(func, None)  # function call
                    if r is not None and r.result != "PASS":  # check: value is not None
                        clause = {  # assignment
                            "standard": "GB50016",  # code
                            "clause_id": func.clause_id,  # code
                            "title": func.name,  # code
                            "text": func.description,  # code
                            "category": func.category.value,  # code
                        }  # code
                        f = _attribution_analyzer.build_finding(
                            r, clause, {}, entities[:5]
                        )  # function call
                        details.append(
                            {  # code
                                "entity_id": "",  # code
                                "entity_type": "missing",  # code
                                "clause_id": f.clause.get("clause_id", ""),  # function call
                                "clause_title": f.clause.get("title", ""),  # function call
                                "result": f.judgement["result"],  # code
                                "extracted_value": 0.0,  # code
                                "required_value": f.extracted_params.get(
                                    "required_value", 1.0
                                ),  # function call
                                "difference": -f.extracted_params.get(
                                    "required_value", 1.0
                                ),  # function call
                                "explanation": f.explanation[:120],  # code
                            }
                        )  # code

            # ── 单文件统计 ────────────────────────────────────
            entity_types = Counter(e["type"] for e in entities)  # function call
            violation_count = Counter(d["clause_id"] for d in details)  # function call

            # ── 评分（P36） ────────────────────────────────────
            score = 100.0  # assignment
            if details:  # condition: details:
                violation_deduction = len(details) * 5.0  # get length
                critical_count = sum(
                    1 for d in details if d.get("severity") == "critical"
                )  # aggregate sum
                major_count = sum(
                    1 for d in details if d.get("severity") == "major"
                )  # aggregate sum
                score = max(
                    0, 100.0 - violation_deduction - critical_count * 10 - major_count * 3
                )  # get maximum

            completed_files += 1  # accumulate
            return {  # return: dict
                "filename": file.filename,  # code
                "file_id": file_id,  # code
                "status": "success",  # code
                "summary": {  # code
                    "total_checks": len(entities) * len(registry_funcs),  # get length
                    "total_entities": len(entities),  # get length
                    "entity_types": dict(entity_types),  # function call
                    "violations": len(details),  # get length
                    "violation_by_clause": dict(violation_count.most_common(10)),  # function call
                    "score": score,  # code
                },  # code
                "details": details[:100],  # code
                "entities": [  # code
                    {
                        "id": e.get("id", e.get("type", "")),
                        "type": e["type"],
                        "bbox": e["bbox"],
                    }  # function call
                    for e in entities  # loop: iterate
                ],  # code
            }  # code

        except Exception as e:
            _review_queue.fail(task_id, str(e))
            completed_files += 1
            return {
                "filename": file.filename,
                "status": "error",
                "error_code": "REVIEW_FAILED",
                "message": str(e),
            }

        # 标记任务完成
        _review_queue.complete(task_id, {"filename": file.filename, "file_id": file_id})

    # ── 并发执行所有文件 ──────────────────────────────────────
    file_tasks = [asyncio.create_task(_review_single_file(f)) for f in files]  # function call
    file_results = await asyncio.gather(*file_tasks)  # function call

    # 汇总变量
    all_details = []  # assignment
    all_entities_list = []  # assignment
    total_violations = 0  # assignment
    total_checks = 0  # assignment
    severity_counter = Counter()  # function call
    entity_type_counter = Counter()  # function call

    for file_result in file_results:  # loop: iterate
        if file_result["status"] == "success":  # condition: file_result["status"] == "success":
            total_violations += file_result["summary"]["violations"]  # accumulate
            total_checks += file_result["summary"]["total_checks"]  # accumulate
            all_details.extend(file_result["details"])  # extend list
            all_entities_list.extend(file_result.get("entities", []))  # extend list
            for d in file_result["details"]:  # loop: iterate
                severity_counter[d.get("severity", "major")] += 1  # function call
            for etype, count in (
                file_result["summary"].get("entity_types", {}).items()
            ):  # loop: iterate
                entity_type_counter[etype] += count  # accumulate

    # ── 交叉分析：跨图纸找出同一违规类别 ─────────────────────
    cross_clause = Counter(d["clause_id"] for d in all_details)  # function call
    cross_analysis = []  # assignment
    for clause_id, count in cross_clause.most_common(10):  # loop: iterate
        involved_files = set()  # function call
        for r in file_results:  # loop: iterate
            if r["status"] != "success":  # condition: r["status"] != "success":
                continue  # code
            for d in r["details"]:  # loop: iterate
                if d["clause_id"] == clause_id:  # condition: d["clause_id"] == clause_id:
                    involved_files.add(r["filename"])  # function call
                    break  # code
        cross_analysis.append(
            {  # code
                "clause_id": clause_id,  # code
                "violations": count,  # code
                "files": len(involved_files),  # get length
                "file_names": list(involved_files)[:5],  # function call
            }
        )  # code

    elapsed = int((time.time() - start) * 1000)  # get current time

    return {  # return: dict
        "status": "success",  # code
        "batch_summary": {  # code
            "total_files": len(files),  # get length
            "success_files": sum(
                1 for r in file_results if r["status"] == "success"
            ),  # aggregate sum
            "failed_files": sum(
                1 for r in file_results if r["status"] != "success"
            ),  # aggregate sum
            "total_violations": total_violations,  # code
            "total_checks": total_checks,  # code
            "total_entities": len(all_entities_list),  # get length
            "processing_time_ms": elapsed,  # code
            # 项目级统计
            "severity_distribution": dict(severity_counter),  # function call
            "entity_type_distribution": dict(entity_type_counter),  # function call
        },  # code
        "cross_analysis": cross_analysis,  # code
        "results": file_results,  # code
    }  # code


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
    effective_types = building_types if building_types else [building_type]  # assignment

    from src.baa_engine.spec_repository import SpecRepository  # import
    from collections import Counter  # stdlib: collections

    repo = SpecRepository()  # function call
    clause_results = Counter()  # function call
    details = []  # assignment
    registry_funcs = _func_registry.list_all()  # check all true

    start = time.time()  # get current time

    # 审查任务队列排队
    task_obj, task_id, queue_position = await _review_queue.wait_and_dequeue("from-data")
    if task_obj is None:
        return {
            "status": "error",
            "error_code": "QUEUE_TIMEOUT",
            "message": "排队超时，请稍后重试",
        }

    try:
        _review_queue.update_progress(task_id, 10.0)

        # 多建筑类型并行匹配：取最严格阈值
        def get_strict_threshold(
            clause_id: str,
        ) -> tuple:  # function: def get_strict_threshold(clause_id: str) -> tuple:
            worst_val, worst_unit, worst_op = None, None, None  # assignment
            for bt in effective_types:  # loop: iterate
                v, u, o = repo.get_threshold(clause_id, bt)  # function call
                if worst_val is None or v > worst_val:  # check: value is None
                    worst_val, worst_unit, worst_op = v, u, o  # assignment
            return worst_val, worst_unit, worst_op  # return

        # ── 逐实体逐函数规范判定 ──────────────────────────────
        for e in entities:  # 循环
            for func in registry_funcs:  # 循环
                threshold_val, unit, op = get_strict_threshold(func.clause_id)  # function call
                func.threshold = threshold_val  # assignment
                func.unit = unit  # assignment
                func.operator = op  # assignment
                r = _func_registry.execute_with_timeout(func, e)  # function call
                if r is None:  # check: value is None
                    continue  # 继续循环
                clause_results[func.clause_id] += 1  # accumulate
                if r.result != "PASS":  # condition: r.result != "PASS":
                    clause = {  # assignment
                        "standard": "GB50016",  # 字段
                        "clause_id": func.clause_id,  # 字段
                        "title": func.name,  # 字段
                        "text": func.description,  # 字段
                        "category": func.category.value,  # 字段
                    }  # code
                    f = _attribution_analyzer.build_finding(
                        r, clause, e, entities[:5]
                    )  # function call
                    details.append(
                        {  # code
                            "entity_id": e.get("id", e.get("type", "")),  # 字段
                            "entity_type": e["type"],  # 字段
                            "clause_id": f.clause.get("clause_id", ""),  # 字段
                            "clause_title": f.clause.get("title", ""),  # 字段
                            "result": f.judgement["result"],  # 字段
                            "extracted_value": f.extracted_params["extracted_value"],  # 字段
                            "required_value": f.extracted_params.get("required_value", 1.2),  # 字段
                            "difference": f.extracted_params.get("difference", 0),  # 字段
                            "severity": f.judgement.get("severity", "major"),  # 字段
                            "explanation": f.explanation[:120],  # 字段
                        }
                    )  # code

        # ── 缺失检查 ──────────────────────────────────────────
        for func in registry_funcs:  # 循环
            if func.category.value != "exist":  # check: OR condition
                continue  # 继续循环
            has_match = any(func.matches(e) for e in entities)  # check any true
            if not has_match:  # check: negated condition
                r = _func_registry.execute_with_timeout(func, None)  # function call
                if r is not None and r.result != "PASS":  # check: value is not None
                    clause = {  # assignment
                        "standard": "GB50016",  # 字段
                        "clause_id": func.clause_id,  # 字段
                        "title": func.name,  # 字段
                        "text": func.description,  # 字段
                        "category": func.category.value,  # 字段
                    }  # code
                    f = _attribution_analyzer.build_finding(
                        r, clause, {}, entities[:5]
                    )  # function call
                    details.append(
                        {  # code
                            "entity_id": "",  # 字段
                            "entity_type": "missing",  # 字段
                            "clause_id": f.clause.get("clause_id", ""),  # 字段
                            "clause_title": f.clause.get("title", ""),  # 字段
                            "result": f.judgement["result"],  # 字段
                            "severity": "critical",  # 字段
                            "extracted_value": 0.0,  # 字段
                            "required_value": f.extracted_params.get("required_value", 1.0),  # 字段
                            "difference": -f.extracted_params.get("required_value", 1.0),  # 字段
                            "explanation": f.explanation[:120],  # 字段
                        }
                    )  # code

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
                "elements": elements,
                "details": details,
                "corrections": corrections,
                "summary": response_data.get("summary", {}),
            }
        except Exception as e:
            response_data["corrections"] = []
            response_data["raw_result"] = {"elements": elements, "details": details}  # 操作

    except Exception as outer_e:
        _review_queue.fail(task_id, str(outer_e))
        raise

    # 标记任务完成
    _review_queue.complete(task_id, response_data)
    response_data["queue_info"] = {
        "task_id": task_id,
        "queue_position": queue_position,
    }
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
            status_code=404, detail={"status": "error", "error_code": "FILE_NOT_FOUND", "message": "文件不存在"}
        )  # 抛出异常

    import ezdxf  # import
    from io import StringIO  # import

    # 异常保护：捕获可能失败的调用
    try:  # 尝试
        doc = ezdxf.readfile(str(file_path))  # function call
        msp = doc.modelspace()  # function call
    except Exception:  # 捕获异常
        raise HTTPException(
            status_code=400, detail={"status": "error", "error_code": "PARSE_FAILED", "message": "无法解析图纸文件"}
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
            status_code=404, detail={"status": "error", "error_code": "FILE_NOT_FOUND", "message": "文件不存在"}
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
            status_code=400, detail={"status": "error", "error_code": "PARSE_FAILED", "message": "无法解析图纸文件"}
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
            status_code=404, detail={"status": "error", "error_code": "FILE_NOT_FOUND", "message": "文件不存在"}
        )  # function call

    # 重新审查（保证使用最新引擎版本）
    import asyncio  # stdlib: async

    loop = asyncio.get_event_loop()  # function call

    result = await loop.run_in_executor(  # assignment
        ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id  # function call
    )  # code
    if not result.success:  # check: negated condition
        raise HTTPException(
            status_code=400, detail={"status": "error", "error_code": "PARSE_FAILED", "message": f"图纸解析失败: {result.error}"}
        )  # function call

    semantic = await loop.run_in_executor(  # assignment
        ENGINE_THREAD_POOL,  # code
        lambda: _semantic_analyzer.analyze(
            result.primitives, result.dimensions, dxf_path=str(file_path)
        ),  # function call
    )  # code
    entities = semantic["entities"]  # assignment

    from src.baa_engine.spec_repository import SpecRepository  # import
    from collections import Counter  # stdlib: collections

    repo = SpecRepository()  # function call
    details = []  # assignment
    registry_funcs = _func_registry.list_all()  # check all true

    start = time.time()  # get current time

    # ── 逐实体逐函数规范判定 ──────────────────────────────
    for e in entities:  # loop: iterate
        for func in registry_funcs:  # loop: iterate
            threshold_val, unit, op = repo.get_threshold(func.clause_id, "civil")  # function call
            try:  # try block
                r = _func_registry.execute_with_timeout(func, e)  # function call
                if r is None:  # check: value is None
                    continue  # code
                clause = {  # assignment
                    "standard": "GB50016",  # code
                    "clause_id": func.clause_id,  # code
                    "title": func.name,  # code
                    "text": func.description,  # code
                    "category": func.category.value,  # code
                }  # code
                f = _attribution_analyzer.build_finding(
                    r, clause, {}, entities[:5]
                )  # function call
                if f.judgement["result"] != "PASS":  # condition: f.judgement["result"] != "PASS":
                    details.append(
                        {  # code
                            "entity_id": e.get("id", ""),  # function call
                            "entity_type": e.get("type", ""),  # function call
                            "clause_id": f.clause.get("clause_id", ""),  # function call
                            "clause_title": f.clause.get("title", ""),  # function call
                            "result": f.judgement["result"],  # code
                            "extracted_value": r.actual,  # code
                            "required_value": threshold_val,  # code
                            "difference": (r.actual or 0) - threshold_val,  # function call
                            "explanation": f.explanation[:120],  # code
                        }
                    )  # code
            except Exception:  # catch exception
                continue  # code

    # ── 缺失检查 ──────────────────────────────────────────
    for func in registry_funcs:  # loop: iterate
        if func.category.value != "exist":  # check: OR condition
            continue  # code
        has_match = any(func.matches(e) for e in entities)  # check any true
        if not has_match:  # check: negated condition
            r = _func_registry.execute_with_timeout(func, None)  # function call
            if r is not None and r.result != "PASS":  # check: value is not None
                clause = {  # assignment
                    "standard": "GB50016",  # code
                    "clause_id": func.clause_id,  # code
                    "title": func.name,  # code
                    "text": func.description,  # code
                    "category": func.category.value,  # code
                }  # code
                f = _attribution_analyzer.build_finding(
                    r, clause, {}, entities[:5]
                )  # function call
                details.append(
                    {  # code
                        "entity_id": "",  # code
                        "entity_type": "missing",  # code
                        "clause_id": f.clause.get("clause_id", ""),  # function call
                        "clause_title": f.clause.get("title", ""),  # function call
                        "result": f.judgement["result"],  # code
                        "extracted_value": 0.0,  # code
                        "required_value": f.extracted_params.get(
                            "required_value", 1.0
                        ),  # function call
                        "difference": -f.extracted_params.get(
                            "required_value", 1.0
                        ),  # function call
                        "explanation": f.explanation[:120],  # code
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

@router.post("/review/compare")  # function call
async def review_compare(  # code
    file1: UploadFile = File(..., description="版本1（旧图纸）"),  # function call
    file2: UploadFile = File(..., description="版本2（新图纸）"),  # function call
    building_type: str = Query(
        "civil", description="建筑类型: civil(民用) / industrial(工业)"
    ),  # function call
    standard: str = Query(
        "GB 50016-2014", description="规范标准: GB 50016-2014 / NFPA 101-2021 / NFPA 5000-2021"
    ),  # function call
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """审查结果对比（Diff）

    上传同一图纸的两个版本，自动分别审查并对比差异：
    - 新增违规：新版新增的违规项
    - 消失违规：旧版有但新版已修复的违规项
    - 变化违规：同一实体值或状态发生变化

    返回结构化 Diff 报告，含变更摘要和逐条详情。
    """
    from src.baa_engine.review_diff import ReviewDiffEngine  # import

    loop = asyncio.get_event_loop()  # function call

    async def _run_review(file: UploadFile) -> tuple:  # function call
        content = await file.read()  # function call
        filename = file.filename or "unknown"  # assignment
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""  # function call

        if ext not in SUPPORTED_FORMATS:  # check: membership test
            raise HTTPException(
                status_code=400,
                detail={  # assignment
                    "status": "error",
                    "error_code": "UNSUPPORTED_FORMAT",  # code
                    "message": f"不支持的文件格式: {ext}",  # code
                },
            )  # code

        file_id = generate_file_id()  # function call
        file_path = store_file(content, file_id, ext)  # function call

        result = await loop.run_in_executor(  # assignment
            ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id  # function call
        )  # code
        if not result.success:  # check: negated condition
            raise HTTPException(
                status_code=400,
                detail={  # assignment
                    "status": "error",
                    "error_code": "PARSE_FAILED",
                    "message": f"图纸解析失败: {result.error}",  # code
                },
            )  # code

        semantic = await loop.run_in_executor(  # assignment
            ENGINE_THREAD_POOL,  # code
            lambda: _semantic_analyzer.analyze(  # code
                result.primitives,
                result.dimensions,  # code
                building_type=building_type,
                dxf_path=str(file_path),  # function call
            ),  # code
        )  # code
        entities = semantic["entities"]  # assignment

        from src.baa_engine.spec_repository import SpecRepository  # import
        from collections import Counter  # stdlib: collections

        repo = SpecRepository()  # function call
        details = []  # assignment
        registry_funcs = _func_registry.list_all()  # check all true

        for e in entities:  # loop: iterate
            for func in registry_funcs:  # loop: iterate
                try:  # try block
                    threshold_val, unit, op = repo.get_threshold(  # assignment
                        func.clause_id, building_type, standard  # code
                    )  # code
                    func.threshold = threshold_val  # assignment
                    func.unit = unit  # assignment
                    func.operator = op  # assignment
                    r = _func_registry.execute_with_timeout(func, e)  # function call
                    if r is not None and r.result != "PASS":  # check: value is not None
                        clause = {  # assignment
                            "standard": standard,  # code
                            "clause_id": func.clause_id,  # code
                            "title": func.name,  # code
                            "text": func.description,  # code
                            "category": func.category.value,  # code
                        }  # code
                        f = _attribution_analyzer.build_finding(
                            r, clause, e, entities[:5]
                        )  # function call
                        details.append(
                            {  # code
                                "entity_id": e.get("id", ""),  # function call
                                "entity_type": e.get("type", ""),  # function call
                                "clause_id": f.clause.get("clause_id", ""),  # function call
                                "clause_title": f.clause.get("title", ""),  # function call
                                "result": f.judgement["result"],  # code
                                "extracted_value": r.actual,  # code
                                "required_value": threshold_val,  # code
                                "difference": (r.actual or 0) - threshold_val,  # function call
                                "explanation": f.explanation[:120],  # code
                            }
                        )  # code
                except Exception:  # catch exception
                    continue  # code

        # 缺失检查：对 EXIST-* 函数检查是否有匹配实体
        for func in registry_funcs:  # loop: iterate
            if func.category.value != "exist":  # check: OR condition
                continue  # code
            has_match = any(func.matches(e) for e in entities)  # check any true
            if not has_match:  # check: negated condition
                r = _func_registry.execute_with_timeout(func, None)  # function call
                if r is not None and r.result != "PASS":  # check: value is not None
                    clause = {  # assignment
                        "standard": standard,  # code
                        "clause_id": func.clause_id,  # code
                        "title": func.name,  # code
                        "text": func.description,  # code
                        "category": func.category.value,  # code
                    }  # code
                    f = _attribution_analyzer.build_finding(
                        r, clause, {}, entities[:5]
                    )  # function call
                    details.append(
                        {  # code
                            "entity_id": "",  # code
                            "entity_type": "missing",  # code
                            "clause_id": f.clause.get("clause_id", ""),  # function call
                            "clause_title": f.clause.get("title", ""),  # function call
                            "result": f.judgement["result"],  # code
                            "extracted_value": 0.0,  # code
                            "required_value": f.extracted_params.get(
                                "required_value", 1.0
                            ),  # function call
                            "difference": -f.extracted_params.get(
                                "required_value", 1.0
                            ),  # function call
                            "explanation": f.explanation[:120],  # code
                        }
                    )  # code

        return filename, details, file_id  # return

    name1, details1, file_id1 = await _run_review(file1)  # function call
    name2, details2, file_id2 = await _run_review(file2)  # function call

    engine = ReviewDiffEngine()  # function call
    report = engine.compare(  # assignment
        details1,
        details2,  # code
        v1_file=name1,  # assignment
        v2_file=name2,  # assignment
        v1_building_type=building_type,  # assignment
        v2_building_type=building_type,  # assignment
        v1_standard=standard,  # assignment
        v2_standard=standard,  # assignment
    )  # code

    result = engine.to_json(report)  # return
    # 注入 file_id 用于前端可视化
    result["v1_file_id"] = file_id1  # assignment
    result["v2_file_id"] = file_id2  # assignment
    return result  # return


# ── 启动入口 ──────────────────────────────────────────────

if __name__ == "__main__":  # condition: __name__ == "__main__":
    """直接运行本文件时启动 Uvicorn 服务器

    生产环境建议通过 Docker 或 systemd 管理进程生命周期。
    """
    import uvicorn  # import
    import sys  # import
    import os  # stdlib: filesystem ops

    port = int(os.getenv("BAA_PORT", "8000"))  # 服务端口
    workers = int(os.getenv("BAA_WORKERS", "4"))  # 默认4 worker

    # 日志输出到项目 data/logs/ 下
    log_dir = DATA_DIR / "logs"  # assignment
    log_dir.mkdir(parents=True, exist_ok=True)  # function call
    log_file = log_dir / "baa-api.log"  # assignment
    print(f"[BAA] 日志路径: {log_file}", flush=True)  # print output
    print(f"[BAA] Worker 数: {workers}", flush=True)  # print output

    uvicorn.run(  # code
        "src.api.baa_api:app",  # 应用模块路径
        host="0.0.0.0",  # assignment
        port=port,  # assignment
        workers=workers,  # assignment
        log_config=None,  # assignment
        access_log=False,  # assignment
        log_level="info",  # assignment
    )  # code


# ── 项目级审查汇总 ─────────────────────────────────────
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
            detail={"status": "error", "error_code": "INVALID_INPUT", "message": "file_ids 不能为空"},
        )
    if len(file_ids) > 50:
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "error_code": "TOO_MANY_FILES", "message": "单次最多汇总50个文件"},
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
