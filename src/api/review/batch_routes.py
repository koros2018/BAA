"""
批量审查端点 — 多文件并发审查 + 跨文件交叉分析。
"""

from fastapi import Depends, HTTPException, Query, File, UploadFile
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict, AsyncGenerator
import json
import psutil

from . import (
    _get_dp,
    _get_sa,
    _get_fr,
    _get_aa,
    _get_pool,
    _get_rq,
    verify_api_key,
    SUPPORTED_FORMATS,
    MAX_FILE_SIZE,
    MAX_FILE_SIZE_MB,
    generate_file_id,
    store_file,
    router,
)
import asyncio
import time
from collections import Counter


@router.post("/batch-review")
async def batch_review(
    files: List[UploadFile] = File(...),
    building_type: str = Query("civil", description="建筑类型: civil(民用) / industrial(工业)"),
    building_types: Optional[List[str]] = Query(None, description="多建筑类型列表（混合建筑场景）"),
    api_key: str = Depends(verify_api_key),
):
    """多文件批量审查

    同时审查最多 20 个图纸文件，返回每个文件的单独审查结果，
    以及跨文件的交叉分析（同一违规类别在多少文件中出现）。
    """
    if len(files) < 1:
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "error_code": "NO_FILES", "message": "请至少上传一个文件"},
        )
    if len(files) > 20:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "TOO_MANY_FILES",
                "message": "单次最多审查20个文件",
            },
        )

    start = time.time()
    loop = asyncio.get_event_loop()
    from src.baa_engine.spec_repository import SpecRepository

    repo = SpecRepository()
    registry_funcs = _get_fr().list_all()
    completed_files = 0

    async def _review_single_file(file: UploadFile) -> Dict:
        """单个文件审查（直接执行，不排队）"""
        nonlocal completed_files

        try:
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
            if ext not in SUPPORTED_FORMATS:
                completed_files += 1
                return {
                    "filename": file.filename,
                    "status": "error",
                    "error_code": "UNSUPPORTED_FORMAT",
                    "message": f"不支持的文件格式: {ext}",
                }

            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                completed_files += 1
                return {
                    "filename": file.filename,
                    "status": "error",
                    "error_code": "FILE_TOO_LARGE",
                    "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",
                }

            file_id = generate_file_id()
            file_path = store_file(content, file_id, ext)

            result = await loop.run_in_executor(
                _get_pool(), _get_dp().parse, str(file_path), file_id
            )
            if not result.success:
                completed_files += 1
                return {
                    "filename": file.filename,
                    "status": "error",
                    "error_code": "PARSE_FAILED",
                    "message": f"图纸解析失败: {result.error}",
                }

            semantic = await loop.run_in_executor(
                _get_pool(),
                lambda: _get_sa().analyze(
                    result.primitives,
                    result.dimensions,
                    building_type=building_type,
                ),
            )
            entities = semantic["entities"]

            effective_types = building_types if building_types else [building_type]
            details = []

            def get_strict_threshold(clause_id: str) -> tuple:
                worst_val, worst_unit, worst_op = None, None, None
                for bt in effective_types:
                    v, u, o = repo.get_threshold(clause_id, bt)
                    if worst_val is None or v > worst_val:
                        worst_val, worst_unit, worst_op = v, u, o
                return worst_val, worst_unit, worst_op

            # P87: 并发执行 entity×func 判定，替代串行嵌套循环
            func_specs = [
                (f, *get_strict_threshold(f.clause_id)) for f in registry_funcs
            ]
            for e in entities:
                batch = _get_fr().execute_batch(e, func_specs)
                for r in batch.values():
                    if r.result == "PASS":
                        continue
                    clause = {
                        "standard": "GB50016",
                        "clause_id": r.clause_id,
                        "title": r.func_name,
                        "text": "",
                        "category": "",
                    }
                    f = _get_aa().build_finding(r, clause, e, entities[:5])
                    details.append(
                        {
                            "entity_id": e.get("id", e.get("type", "")),
                            "entity_type": e["type"],
                            "clause_id": r.clause_id,
                            "clause_title": r.func_name,
                            "result": "FAIL" if r.result != "PASS" else "PASS",
                            "extracted_value": r.params.get("extracted_value", 0.0),
                            "required_value": r.params.get("required_value", r.threshold),
                            "difference": r.delta,
                            "explanation": r.params.get("note", "")[:120],
                            "confidence": r.confidence,
                            "severity": r.severity.value,
                        }
                    )

            # 缺失检查：仅当函数目标实体类型与图纸实体类型有交集时才执行
            entity_types_in_drawing = set(e.get("type", "") for e in entities)
            missing_batch = _get_fr().execute_missing_batch(entity_types_in_drawing, registry_funcs)
            for r in missing_batch.values():
                if r.result == "PASS":
                    continue
                clause = {
                    "standard": "GB50016",
                    "clause_id": r.clause_id,
                    "title": r.func_name,
                    "text": "",
                    "category": "",
                }
                f = _get_aa().build_finding(r, clause, {}, entities[:5])
                details.append(
                    {
                        "entity_id": "",
                        "entity_type": "missing",
                        "clause_id": r.clause_id,
                        "clause_title": r.func_name,
                        "func_id": r.func_id,
                        "result": "FAIL",
                        "extracted_value": 0.0,
                        "required_value": r.threshold,
                        "difference": -r.threshold,
                        "explanation": r.params.get("note", "")[:120],
                        "severity": "critical",
                        "confidence": r.confidence,
                    }
                )

            entity_types = Counter(e["type"] for e in entities)
            violation_count = Counter(d["clause_id"] for d in details)

            # 评分（P36）
            score = 100.0
            if details:
                violation_deduction = len(details) * 5.0
                critical_count = sum(1 for d in details if d.get("severity") == "critical")
                major_count = sum(1 for d in details if d.get("severity") == "major")
                score = max(0, 100.0 - violation_deduction - critical_count * 10 - major_count * 3)

            completed_files += 1
            return {
                "filename": file.filename,
                "file_id": file_id,
                "status": "success",
                "summary": {
                    "total_checks": len(entities) * len(registry_funcs),
                    "total_entities": len(entities),
                    "entity_types": dict(entity_types),
                    "violations": len(details),
                    "violation_by_clause": dict(violation_count.most_common(10)),
                    "score": score,
                },
                "details": details[:100],
                "entities": [
                    {
                        "id": e.get("id", e.get("type", "")),
                        "type": e["type"],
                        "bbox": e["bbox"],
                    }
                    for e in entities
                ],
            }

        except Exception as e:
            completed_files += 1
            return {
                "filename": file.filename,
                "status": "error",
                "error_code": "REVIEW_FAILED",
                "message": str(e),
            }

    file_tasks = [asyncio.create_task(_review_single_file(f)) for f in files]
    file_results = await asyncio.gather(*file_tasks)

    all_details = []
    all_entities_list = []
    total_violations = 0
    total_checks = 0
    severity_counter = Counter()
    entity_type_counter = Counter()

    for file_result in file_results:
        if file_result["status"] == "success":
            total_violations += file_result["summary"]["violations"]
            total_checks += file_result["summary"]["total_checks"]
            all_details.extend(file_result["details"])
            all_entities_list.extend(file_result.get("entities", []))
            for d in file_result["details"]:
                severity_counter[d.get("severity", "major")] += 1
            for etype, count in file_result["summary"].get("entity_types", {}).items():
                entity_type_counter[etype] += count

    # 交叉分析：跨图纸找出同一违规类别
    cross_clause = Counter(d["clause_id"] for d in all_details)
    cross_analysis = []
    for clause_id, count in cross_clause.most_common(10):
        involved_files = set()
        for r in file_results:
            if r["status"] != "success":
                continue
            for d in r["details"]:
                if d["clause_id"] == clause_id:
                    involved_files.add(r["filename"])
                    break
        cross_analysis.append(
            {
                "clause_id": clause_id,
                "violations": count,
                "files": len(involved_files),
                "file_names": list(involved_files)[:5],
            }
        )

    elapsed = int((time.time() - start) * 1000)

    return {
        "status": "success",
        "batch_summary": {
            "total_files": len(files),
            "success_files": sum(1 for r in file_results if r["status"] == "success"),
            "failed_files": sum(1 for r in file_results if r["status"] != "success"),
            "total_violations": total_violations,
            "total_checks": total_checks,
            "total_entities": len(all_entities_list),
            "processing_time_ms": elapsed,
            "severity_distribution": dict(severity_counter),
            "entity_type_distribution": dict(entity_type_counter),
        },
        "cross_analysis": cross_analysis,
        "results": file_results,
    }


# ═══════════════════════════════════════════════════════════════
# P87 Phase 2: SSE 流式批量审查 — 实时进度推送
# ═══════════════════════════════════════════════════════════════


@router.post("/batch-review-stream")
async def batch_review_stream(
    files: List[UploadFile] = File(...),
    building_type: str = Query("civil", description="建筑类型: civil(民用) / industrial(工业)"),
    building_types: Optional[List[str]] = Query(None, description="多建筑类型列表"),
    api_key: str = Depends(verify_api_key),
):
    """多文件批量审查 — SSE 流式推送实时进度

    每个文件在关键阶段推送进度事件：
    - file.queued / file.parsing / file.semantic / file.checking / file.done / file.error
    - batch.done 标记全部完成，含跨文件汇总
    """
    if len(files) > 20:
        raise HTTPException(status_code=400,
            detail={"status": "error", "error_code": "TOO_MANY_FILES"})

    from src.baa_engine.spec_repository import SpecRepository
    from dataclasses import replace

    loop = asyncio.get_event_loop()
    repo = SpecRepository()
    registry_funcs = _get_fr().list_all()
    # 事件队列：任务 → SSE 消费者
    event_queue: "asyncio.Queue[dict]" = asyncio.Queue(maxsize=200)

    def _make_finding_detail(r, clause, entity, entity_type=""):
        f = _get_aa().build_finding(r, clause, entity, [])
        return {
            "entity_id": entity.get("id", "") if isinstance(entity, dict) else "",
            "entity_type": entity_type or entity.get("type", ""),
            "clause_id": r.clause_id,
            "clause_title": r.func_name,
            "result": "FAIL",
            "extracted_value": r.params.get("extracted_value", 0.0),
            "required_value": r.params.get("required_value", r.threshold),
            "difference": r.delta,
            "explanation": r.params.get("note", "")[:120],
            "confidence": r.confidence,
            "severity": r.severity.value,
        }

    async def _stream_review_one(idx: int, file: UploadFile) -> Dict:
        """单文件审查，阶段事件通过 queue 推送（P94: 不排队，直接执行）"""
        file_name = file.filename or f"file_{idx}"
        try:
            await event_queue.put({"event": "file.queued", "index": idx, "filename": file_name})

            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
            if ext not in SUPPORTED_FORMATS:
                await event_queue.put({"event": "file.error", "index": idx, "filename": file_name,
                    "error_code": "UNSUPPORTED_FORMAT"})
                return {"filename": file_name, "status": "error", "error_code": "UNSUPPORTED_FORMAT"}

            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                await event_queue.put({"event": "file.error", "index": idx, "filename": file_name,
                    "error_code": "FILE_TOO_LARGE"})
                return {"filename": file_name, "status": "error", "error_code": "FILE_TOO_LARGE"}

            file_id = generate_file_id()
            file_path = store_file(content, file_id, ext)
            avail_mb = psutil.virtual_memory().available / (1024 * 1024)
            if avail_mb < 2048:
                await event_queue.put({
                    "event": "file.error", "index": idx, "filename": file_name,
                    "error_code": "LOW_MEMORY",
                    "message": f"系统可用内存不足（{avail_mb:.0f}MB < 2048MB），请稍后重试"})
                return {"filename": file_name, "status": "error", "error_code": "LOW_MEMORY"}

            await event_queue.put({"event": "file.parsing", "index": idx, "filename": file_name, "file_id": file_id})

            result = await loop.run_in_executor(
                _get_pool(), _get_dp().parse, str(file_path), file_id)
            if not result.success:
                await event_queue.put({"event": "file.error", "index": idx, "filename": file_name,
                    "error_code": "PARSE_FAILED", "message": str(result.error)})
                return {"filename": file_name, "status": "error", "error_code": "PARSE_FAILED"}

            await event_queue.put({"event": "file.semantic", "index": idx, "filename": file_name})
            semantic = await loop.run_in_executor(
                _get_pool(), lambda: _get_sa().analyze(
                    result.primitives, result.dimensions, building_type=building_type))
            entities = semantic["entities"]
            await event_queue.put({
                "event": "file.checking", "index": idx, "filename": file_name,
                "entity_count": len(entities)})

            effective_types = building_types if building_types else [building_type]
            details = []

            def get_strict_threshold(clause_id: str) -> tuple:
                worst_val, worst_unit, worst_op = None, None, None
                for bt in effective_types:
                    v, u, o = repo.get_threshold(clause_id, bt)
                    if worst_val is None or v > worst_val:
                        worst_val, worst_unit, worst_op = v, u, o
                return worst_val, worst_unit, worst_op

            func_specs = [(f, *get_strict_threshold(f.clause_id)) for f in registry_funcs]
            for e in entities:
                batch = _get_fr().execute_batch(e, func_specs)
                for r in batch.values():
                    if r.result == "PASS":
                        continue
                    clause = {"standard": "GB50016", "clause_id": r.clause_id,
                        "title": r.func_name, "text": "", "category": ""}
                    details.append(_make_finding_detail(r, clause, e))

            entity_types_set = set(e.get("type", "") for e in entities)
            missing_batch = _get_fr().execute_missing_batch(entity_types_set, registry_funcs)
            for r in missing_batch.values():
                if r.result == "PASS":
                    continue
                clause = {"standard": "GB50016", "clause_id": r.clause_id,
                    "title": r.func_name, "text": "", "category": ""}
                details.append(_make_finding_detail(r, clause, {}, "missing"))

            entity_types = Counter(e["type"] for e in entities)
            violation_count = Counter(d["clause_id"] for d in details)
            score = 100.0
            if details:
                critical_count = sum(1 for d in details if d.get("severity") == "critical")
                major_count = sum(1 for d in details if d.get("severity") == "major")
                score = max(0, 100.0 - len(details) * 5.0 - critical_count * 10 - major_count * 3)

            result_obj = {
                "filename": file_name, "file_id": file_id, "status": "success",
                "summary": {
                    "total_checks": len(entities) * len(registry_funcs),
                    "total_entities": len(entities),
                    "entity_types": dict(entity_types),
                    "violations": len(details),
                    "violation_by_clause": dict(violation_count.most_common(10)),
                    "score": score,
                },
                "details": details[:100],
                "entities": [{"id": e.get("id", e.get("type", "")), "type": e["type"],
                    "bbox": e["bbox"]} for e in entities],
            }
            await event_queue.put({
                "event": "file.done", "index": idx, "filename": file_name,
                "violations": len(details), "score": score,
                "entity_count": len(entities)})
            return result_obj

        except Exception as e:
            msg = str(e)
            await event_queue.put({"event": "file.error", "index": idx,
                "filename": file_name, "error_code": "REVIEW_FAILED", "message": msg[:200]})
            return {"filename": file_name, "status": "error", "error_code": "REVIEW_FAILED",
                "message": msg[:200]}

    # 启动所有文件并发审查
    file_tasks = [asyncio.create_task(_stream_review_one(i, f))
                  for i, f in enumerate(files)]
    # 完成信号
    completion_done = asyncio.Event()

    async def _drain_and_yield():
        """从 queue 消费事件，遇到 sentinel 后 yield 结束事件"""
        while True:
            try:
                evt = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                if evt.get("event") == "SIGNAL_DONE":
                    return
                yield evt
            except asyncio.TimeoutError:
                continue

    async def _wait_and_signal():
        """等待所有文件完成，然后放入结束信号"""
        all_results = await asyncio.gather(*file_tasks)
        # 跨文件交叉分析
        all_details = []
        total_violations = 0
        total_entities = 0
        for r in all_results:
            if r["status"] == "success":
                total_violations += r["summary"]["violations"]
                total_entities += r["summary"]["total_entities"]
                all_details.extend(r.get("details", []))

        cross_clause = Counter(d["clause_id"] for d in all_details)
        cross_analysis = []
        for clause_id, count in cross_clause.most_common(10):
            involved_files = set()
            for r in all_results:
                if r["status"] != "success":
                    continue
                if any(d["clause_id"] == clause_id for d in r.get("details", [])):
                    involved_files.add(r.get("filename", ""))
            if involved_files:
                cross_analysis.append({
                    "clause_id": clause_id, "violations": count,
                    "files": len(involved_files),
                    "file_names": list(involved_files)[:5],
                })

        await event_queue.put({
            "event": "batch.done",
            "total_files": len(files),
            "success_files": sum(1 for r in all_results if r["status"] == "success"),
            "failed_files": sum(1 for r in all_results if r["status"] != "success"),
            "total_violations": total_violations,
            "total_entities": total_entities,
            "cross_analysis": cross_analysis,
            "results": all_results,
        })
        await event_queue.put({"event": "SIGNAL_DONE"})
        completion_done.set()

    # 启动等待任务
    waiter = asyncio.create_task(_wait_and_signal())

    async def event_generator():
        async for evt in _drain_and_yield():
            line = f"data: {json.dumps(evt, ensure_ascii=False, default=str)}\n\n"
            yield line
        # 确保等待器不丢
        if not waiter.done():
            try:
                await asyncio.wait_for(waiter, timeout=60)
            except asyncio.TimeoutError:
                pass
        # 收尾
        try:
            await event_queue.put({"event": "SIGNAL_DONE"})
        except asyncio.QueueFull:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
