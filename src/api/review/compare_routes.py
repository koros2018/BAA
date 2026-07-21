"""
审查模块 — Compare Routes
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
            _get_pool(), _get_dp().parse, str(file_path), file_id  # function call
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
            _get_pool(),  # code
            lambda: _get_sa().analyze(  # code
                result.primitives,
                result.dimensions,  # code
                building_type=building_type,
                dxf_path=str(file_path),  # function call
            ),  # code
        )  # code
        entities = semantic["entities"]  # assignment

        from src.baa_engine.spec_repository import SpecRepository  # import

        repo = SpecRepository()  # function call
        details = []  # assignment
        registry_funcs = _get_fr().list_all()  # check all true

        for e in entities:  # loop: iterate
            for func in registry_funcs:  # loop: iterate
                try:  # try block
                    threshold_val, unit, op = repo.get_threshold(  # assignment
                        func.clause_id, building_type, standard  # code
                    )  # code
                    func.threshold = threshold_val  # assignment
                    func.unit = unit  # assignment
                    func.operator = op  # assignment
                    r = _get_fr().execute_with_timeout(func, e)  # function call
                    if r is not None and r.result != "PASS":  # check: value is not None
                        clause = {  # assignment
                            "standard": standard,  # code
                            "clause_id": func.clause_id,  # code
                            "title": func.name,  # code
                            "text": func.description,  # code
                            "category": func.category.value,  # code
                        }  # code
                        f = _get_aa().build_finding(r, clause, e, entities[:5])  # function call
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

        # 缺失检查：对 EXIST-* 函数检查是否有匹配实体
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
                        "standard": standard,  # code
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
