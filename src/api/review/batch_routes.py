"""
批量审查端点 — 多文件并发审查 + 跨文件交叉分析。
"""

from fastapi import Depends, HTTPException, Query, File, UploadFile
from typing import Optional, List, Dict

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
        """单个文件审查（独立执行）"""
        nonlocal completed_files

        temp_file_id = generate_file_id()
        task_obj, task_id, queue_position = await _get_rq().wait_and_dequeue(temp_file_id)
        if task_obj is None:
            completed_files += 1
            return {
                "filename": file.filename,
                "status": "error",
                "error_code": "QUEUE_TIMEOUT",
                "message": "排队超时，请稍后重试",
            }

        try:
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
            if ext not in SUPPORTED_FORMATS:
                completed_files += 1
                _get_rq().fail(task_id, f"不支持的文件格式: {ext}")
                return {
                    "filename": file.filename,
                    "status": "error",
                    "error_code": "UNSUPPORTED_FORMAT",
                    "message": f"不支持的文件格式: {ext}",
                }

            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                completed_files += 1
                _get_rq().fail(task_id, "文件过大")
                return {
                    "filename": file.filename,
                    "status": "error",
                    "error_code": "FILE_TOO_LARGE",
                    "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",
                }

            file_id = generate_file_id()
            file_path = store_file(content, file_id, ext)

            _get_rq().update_progress(task_id, 10.0)
            result = await loop.run_in_executor(
                _get_pool(), _get_dp().parse, str(file_path), file_id
            )
            if not result.success:
                completed_files += 1
                _get_rq().fail(task_id, result.error)
                return {
                    "filename": file.filename,
                    "status": "error",
                    "error_code": "PARSE_FAILED",
                    "message": f"图纸解析失败: {result.error}",
                }

            _get_rq().update_progress(task_id, 50.0)
            semantic = await loop.run_in_executor(
                _get_pool(),
                lambda: _get_sa().analyze(
                    result.primitives,
                    result.dimensions,
                    building_type=building_type,
                ),
            )
            entities = semantic["entities"]
            _get_rq().update_progress(task_id, 70.0)

            effective_types = building_types if building_types else [building_type]
            details = []

            def get_strict_threshold(clause_id: str) -> tuple:
                worst_val, worst_unit, worst_op = None, None, None
                for bt in effective_types:
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
                                "confidence": r.confidence,
                                "severity": r.severity.value,
                            }
                        )

            # 缺失检查：仅当函数目标实体类型与图纸实体类型有交集时才执行
            entity_types_in_drawing = set(e.get("type", "") for e in entities)
            for func in registry_funcs:
                if func.category.value != "exist":
                    continue
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
            _get_rq().fail(task_id, str(e))
            completed_files += 1
            return {
                "filename": file.filename,
                "status": "error",
                "error_code": "REVIEW_FAILED",
                "message": str(e),
            }

        _get_rq().complete(task_id, {"filename": file.filename, "file_id": file_id})

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
