"""
管理模块路由（admin/* + EMA2/* + feedbacks/*）
从 baa_api.py 拆分，使用 APIRouter 注册
"""

from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Request
import src.api.api_globals as _ag  # noqa: F401
from src.api.api_globals import get_key_manager  # noqa: F401
import os  # environment
from datetime import datetime  # date/time
import uuid  # unique id
import time  # timing
import asyncio  # async

router = APIRouter()


# ── API密钥管理端点 ──────────────────────────────────


@router.post("/admin/keys", tags=["admin"])  # function call
async def create_api_key(  # code
    body: dict,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(_ag.verify_api_key),  # function call
    _admin: str = Depends(_ag.require_admin),  # function call
):  # code
    """创建新的API Key（需要admin权限）"""
    km = get_key_manager()  # function call

    permission = body.get("permission", "write")  # function call
    ttl_days = body.get("ttl_days", 90)  # function call
    label = body.get("label", "")  # function call

    # 异常保护：捕获可能失败的调用
    try:  # 尝试
        result = km.generate_key(  # assignment
            permission=permission,  # assignment
            ttl_days=ttl_days,  # assignment
            label=label,  # assignment
            created_by=api_key or "anonymous",  # assignment
        )  # code
    except ValueError as e:  # 捕获异常
        raise HTTPException(
            status_code=400,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "INVALID_PARAM",  # 字段
                "message": str(e),  # 字段
            },
        )  # code

    return {  # return: dict
        "status": "success",  # 字段
        "data": result,  # 字段
        "warning": "请立即保存 raw_key，创建后不再显示",  # 字段
    }  # code


@router.get("/admin/keys", tags=["admin"])  # function call
async def list_api_keys(  # code
    include_disabled: bool = Query(False),  # function call
    include_raw: bool = Query(
        False, description="是否返回解密后的 raw_key（密钥详情时使用）"
    ),  # function call
    request: Request = None,  # assignment
    api_key: str = Depends(_ag.verify_api_key),  # function call
    _admin: str = Depends(_ag.require_admin),  # function call
):  # code
    """列出所有API Key"""
    km = get_key_manager()  # function call
    keys = km.list_keys(include_disabled=include_disabled, include_raw=include_raw)  # function call
    stats = km.get_usage_stats()  # function call

    # 遍历处理
    for k in keys:  # 循环
        k_id = k["key_id"]  # assignment
        if k_id in stats:  # check: membership test
            k["usage"] = stats[k_id]  # 操作

    return {  # return: dict
        "status": "success",  # 字段
        "data": keys,  # 字段
        "total": len(keys),  # 字段
    }  # code


@router.get("/admin/keys/stats", tags=["admin"])  # function call
async def api_key_stats(  # code
    request: Request = None,  # assignment
    api_key: str = Depends(_ag.verify_api_key),  # function call
    _admin: str = Depends(_ag.require_admin),  # function call
):  # code
    """API Key用量统计"""
    km = get_key_manager()  # function call

    stats = km.get_usage_stats()  # function call
    keys = km.list_keys(include_disabled=True)  # function call

    return {  # return: dict
        "status": "success",  # 字段
        "data": {  # 字段
            "keys": stats,  # 字段
            "summary": {  # 字段
                "total": len(keys),  # 字段
                "active": len([k for k in keys if k.get("enabled")]),  # 字段
                "disabled": len([k for k in keys if not k.get("enabled")]),  # 字段
                "total_calls": sum(s.get("total_calls", 0) for s in stats.values()),  # 字段
            },  # code
        },  # code
    }  # code


@router.get("/admin/keys/{key_id}", tags=["admin"])  # function call
async def get_api_key_detail(  # code
    key_id: str,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(_ag.verify_api_key),  # function call
    _admin: str = Depends(_ag.require_admin),  # function call
):  # code
    """获取单个API Key详情（含解密后的 raw_key）"""
    km = get_key_manager()  # function call
    keys = km.list_keys(include_disabled=True, include_raw=True)  # function call
    for k in keys:  # 循环
        if k["key_id"] == key_id:  # condition: k["key_id"] == key_id:
            stats = km.get_usage_stats(key_id)  # function call
            k["usage"] = stats  # 操作
            return {"status": "success", "data": k}  # return: dict
    raise HTTPException(
        status_code=404,
        detail={  # 抛出异常
            "status": "error",
            "error_code": "NOT_FOUND",  # 字段
            "message": f"密钥不存在: {key_id}",  # 字段
        },
    )  # code


@router.post("/admin/keys/{key_id}/revoke", tags=["admin"])  # function call
async def revoke_api_key(  # code
    key_id: str,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(_ag.verify_api_key),  # function call
    _admin: str = Depends(_ag.require_admin),  # function call
):  # code
    """撤销API Key"""
    km = get_key_manager()  # function call

    # 根据条件判断分支：if km.revoke_key(key_id)
    if km.revoke_key(key_id):  # condition: km.revoke_key(key_id):
        return {"status": "success", "message": f"密钥 {key_id} 已撤销"}  # return: dict
    raise HTTPException(
        status_code=404,
        detail={  # 抛出异常
            "status": "error",
            "error_code": "NOT_FOUND",  # 字段
            "message": f"密钥不存在: {key_id}",  # 字段
        },
    )  # code


@router.post("/admin/keys/{key_id}/rotate", tags=["admin"])  # function call
async def rotate_api_key(  # code
    key_id: str,  # 操作
    body: dict,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(_ag.verify_api_key),  # function call
    _admin: str = Depends(_ag.require_admin),  # function call
):  # code
    """轮换API Key（生成新密钥值，旧密钥失效）"""
    km = get_key_manager()  # function call
    new_ttl = body.get("new_ttl_days", body.get("new_ttl"))  # 从 body 提取
    result = km.rotate_key(key_id, new_ttl_days=new_ttl)  # function call
    if result:  # condition: result:
        return {  # return: dict
            "status": "success",  # 字段
            "data": result,  # 字段
            "warning": "旧密钥已失效，请立即保存新 raw_key",  # 字段
        }  # code
    raise HTTPException(
        status_code=404,
        detail={  # 抛出异常
            "status": "error",
            "error_code": "NOT_FOUND",  # 字段
            "message": f"密钥不存在或已禁用: {key_id}",  # 字段
        },
    )  # code


@router.delete("/admin/keys/{key_id}", tags=["admin"])  # function call
async def delete_api_key(  # code
    key_id: str,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(_ag.verify_api_key),  # function call
    _admin: str = Depends(_ag.require_admin),  # function call
):  # code
    """物理删除API Key（不可恢复）"""
    km = get_key_manager()  # function call
    if km.delete_key(key_id):  # condition: km.delete_key(key_id):
        return {"status": "success", "message": f"密钥 {key_id} 已永久删除"}  # return: dict
    raise HTTPException(
        status_code=404,
        detail={  # 抛出异常
            "status": "error",
            "error_code": "NOT_FOUND",  # 字段
            "message": f"密钥不存在: {key_id}",  # 字段
        },
    )  # code


@router.post("/admin/keys/verify", tags=["admin"])  # function call
async def verify_api_key_raw(  # code
    body: dict,  # 操作
    request: Request = None,  # assignment
):  # code
    """验证原始API Key是否有效（无需admin权限，供前端导入时校验）"""
    raw_key = body.get("raw_key", "")  # function call
    if not raw_key:  # check: negated condition
        return {"status": "error", "valid": False, "message": "请提供 raw_key"}  # return: dict

    km = get_key_manager()  # function call
    key_info = km.validate_key(raw_key)  # function call
    if key_info and key_info.get("enabled", True):  # check: AND condition
        return {  # return: dict
            "status": "success",  # 字段
            "valid": True,  # 字段
            "key_info": {  # 字段
                "key_id": key_info.get("key_id"),  # 字段
                "label": key_info.get("label"),  # 字段
                "permission": key_info.get("permission"),  # 字段
                "expires_at": key_info.get("expires_at"),  # 字段
                "created_at": key_info.get("created_at"),  # 字段
            },  # code
        }  # code
    else:  # 否则
        return {  # return: dict
            "status": "success",  # 字段
            "valid": False,  # 字段
            "message": "密钥无效或已过期/撤销",  # 字段
        }  # code


@router.get("/admin/bootstrap-key", tags=["admin"])  # function call
async def bootstrap_admin_key():  # function call
    """获取前端密钥管理页使用的管理令牌（bootstrap 专用端点，设计如此）

    开发模式（BAA_API_KEY 未设置）时返回空字符串，
    此时后端 _ag.require_admin 不校验令牌，前端直接发请求即可。
    生产模式时返回环境变量中的 admin key。
    """
    env_key = os.getenv("BAA_API_KEY", "")  # function call
    return {  # return: dict
        "status": "success",  # 字段
        "admin_key": env_key,  # 字段
        "mode": "production" if env_key else "development",  # 字段
    }  # code


# ── EMA2 第三方对接 API ───────────────────────────────────


async def _fire_webhook(webhook_url: str, payload: dict) -> bool:  # function call
    """发送 Webhook 回调通知（异步，不阻塞主流程）

    Args:
        webhook_url: 回调目标 URL
        payload: 发送的 JSON 数据

    Returns:
        bool: 是否发送成功
    """
    import httpx  # import

    try:  # 尝试
        async with httpx.AsyncClient(timeout=10.0) as client:  # function call
            resp = await client.post(webhook_url, json=payload)  # function call
            return resp.status_code == 200  # return
    # 异常处理
    except Exception:  # 捕获异常
        return False  # return: boolean


async def _dispatch_webhooks(event: str, payload: dict) -> None:  # function call
    """遍历注册 Webhook 列表，按 events 过滤后并行发送

    P71：注册列表中的 webhook 默认对所有任务生效，
    per-task 的 webhook_url 在 _run_review_task 中单独处理。
    """
    tasks = []
    for wh in list(_ag._webhooks.values()):  # 遍历注册的 webhook
        if not wh.get("active"):  # 跳过已禁用的
            continue
        events = wh.get("events", "completed").split(",")
        if event not in events and "all" not in events:
            continue
        tasks.append(_fire_webhook(wh["url"], payload))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)  # 并行发送，不阻塞


async def _run_review_task(
    task_id: str, file_path: str, building_type: str, webhook_url: str = None
):  # function call
    """后台执行异步审查任务

    在后台线程中执行完整的审查流程：解析→语义分析→规范判定→缺失检查。
    完成后更新 _ag._tasks 存储中的状态，并根据配置触发 Webhook 回调。
    """
    _ag._tasks[task_id]["status"] = "running"  # 操作
    _ag._tasks[task_id]["updated_at"] = datetime.now().isoformat()  # 操作

    # 异常保护：捕获可能失败的调用
    try:  # 尝试
        start = time.time()  # get current time
        loop = asyncio.get_event_loop()  # function call

        # ── Step 1: 图纸解析 ─────────────────────────────────
        result = await loop.run_in_executor(  # assignment
            _ag.ENGINE_THREAD_POOL, _ag._drawing_parser.parse, str(file_path), task_id  # 操作
        )  # code
        if not result.success:  # check: negated condition
            _ag._tasks[task_id]["status"] = "failed"  # 操作
            _ag._tasks[task_id]["error"] = f"解析失败: {result.error}"  # 操作
            _ag._tasks[task_id]["updated_at"] = datetime.now().isoformat()  # 操作
            if webhook_url:  # condition: webhook_url:
                await _fire_webhook(
                    webhook_url,
                    {  # 操作
                        "task_id": task_id,
                        "status": "failed",
                        "error": _ag._tasks[task_id]["error"],  # 字段
                    },
                )  # code
            # P71: 同时触发注册列表中的 Webhook
            await _dispatch_webhooks(
                "failed",
                {
                    "task_id": task_id,
                    "status": "failed",
                    "error": _ag._tasks[task_id]["error"],
                    "filename": _ag._tasks[task_id].get("filename", ""),
                },
            )
            return  # code

        # ── Step 2: 语义分析 ─────────────────────────────────
        semantic = await loop.run_in_executor(  # assignment
            _ag.ENGINE_THREAD_POOL,  # 解包
            lambda: _ag._semantic_analyzer.analyze(  # 操作
                result.primitives, result.dimensions, building_type=building_type  # 解包
            ),  # code
        )  # code
        entities = semantic["entities"]  # assignment

        # ── Step 3: 规范判定 ─────────────────────────────────
        details = []  # assignment
        for e in entities:  # 循环
            for func in _ag._func_registry.list_all():  # 循环
                threshold_val, unit, op = _ag._spec_repo.get_threshold(
                    func.clause_id, building_type
                )  # function call
                func.threshold = threshold_val  # assignment
                func.unit = unit  # assignment
                func.operator = op  # assignment
                r = _ag._func_registry.execute_with_timeout(func, e)  # function call
                if r is None or r.result == "PASS":  # check: value is None
                    continue  # 继续循环
                clause = {  # assignment
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # code
                f = _ag._attribution_analyzer.build_finding(
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
                        "explanation": f.explanation[:120],  # 字段
                        "severity": f.judgement.get("severity", "major"),  # 字段
                    }
                )  # code

        # ── Step 4: 缺失检查 ─────────────────────────────────
        for func in _ag._func_registry.list_all():  # 循环
            if func.category.value != "exist":  # check: OR condition
                continue  # 继续循环
            if not any(func.matches(e) for e in entities):  # check: membership test
                r = _ag._func_registry.execute_with_timeout(func, None)  # function call
                if r is not None and r.result != "PASS":  # check: value is not None
                    clause = {  # assignment
                        "standard": "GB50016",  # 字段
                        "clause_id": func.clause_id,  # 字段
                        "title": func.name,  # 字段
                        "text": func.description,  # 字段
                        "category": func.category.value,  # 字段
                    }  # code
                    f = _ag._attribution_analyzer.build_finding(
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
                            "severity": f.judgement.get("severity", "major"),  # 字段
                        }
                    )  # code

        elapsed = int((time.time() - start) * 1000)  # get current time

        # ── 存储结果 ────────────────────────────────────────
        _ag._tasks[task_id]["status"] = "completed"  # 操作
        _ag._tasks[task_id]["result"] = {  # 操作
            "summary": {  # 字段
                "total_entities": len(entities),  # 字段
                "violations": len(details),  # 字段
                "entity_types": dict(Counter(e["type"] for e in entities)),  # 字段
            },  # code
            "details": details,  # 字段
            "processing_time_ms": elapsed,  # 字段
        }  # code
        _ag._tasks[task_id]["updated_at"] = datetime.now().isoformat()  # 操作

        # ── Webhook 回调通知 ─────────────────────────────────
        if webhook_url:  # condition: webhook_url:
            await _fire_webhook(
                webhook_url,
                {  # 操作
                    "task_id": task_id,
                    "status": "completed",  # 字段
                    "violations": len(details),
                    "entities": len(entities),  # 字段
                    "processing_time_ms": elapsed,  # 字段
                },
            )  # code

            # P71: 同时触发注册列表中的 Webhook（与 per-task webhook 并行）
            await _dispatch_webhooks(
                "completed",
                {
                    "task_id": task_id,
                    "status": "completed",
                    "violations": len(details),
                    "entities": len(entities),
                    "processing_time_ms": elapsed,
                    "filename": _ag._tasks[task_id].get("filename", ""),
                },
            )

    # 异常处理
    except Exception as e:  # 捕获异常
        _ag._tasks[task_id]["status"] = "failed"  # 操作
        _ag._tasks[task_id]["error"] = str(e)  # 操作
        _ag._tasks[task_id]["updated_at"] = datetime.now().isoformat()  # 操作
        if webhook_url:  # condition: webhook_url:
            await _fire_webhook(
                webhook_url,
                {"task_id": task_id, "status": "failed", "error": str(e)},  # 操作  # 字段
            )  # code
        # P71: 同时触发注册列表中的 Webhook
        await _dispatch_webhooks(
            "failed",
            {
                "task_id": task_id,
                "status": "failed",
                "error": str(e),
                "filename": _ag._tasks[task_id].get("filename", ""),
            },
        )


@router.post("/api/v1/tasks", tags=["EMA2"])  # function call
async def create_review_task(  # code
    file: UploadFile = File(...),  # function call
    building_type: str = Query("civil", description="建筑类型: civil/industrial"),  # function call
    webhook_url: str = Query("", description="回调通知 URL（可选）"),  # function call
    api_key: str = Depends(_ag.verify_api_key),  # function call
):  # code
    """创建异步审查任务（EMA2 对接）

    上传图纸文件，创建异步审查任务。任务完成后通过轮询或 Webhook 获取结果。
    """
    filename = file.filename or "unknown"  # assignment
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""  # function call
    if ext not in _ag.SUPPORTED_FORMATS:  # check: membership test
        raise HTTPException(
            status_code=400,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "UNSUPPORTED_FORMAT",  # 字段
                "message": f"不支持的文件格式: {ext}",  # 字段
            },
        )  # code

    content = await file.read()  # function call
    if len(content) > _ag.MAX_FILE_SIZE:  # check: numeric comparison
        raise HTTPException(
            status_code=400,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "FILE_TOO_LARGE",  # 字段
                "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{_ag.MAX_FILE_SIZE_MB}MB",  # 字段
            },
        )  # code

    file_id = _ag.generate_file_id()  # function call
    file_path = store_file(content, file_id, ext)  # function call

    # 创建任务
    task_id = str(uuid.uuid4())[:8]  # function call
    _ag._tasks[task_id] = {  # assignment
        "task_id": task_id,  # 字段
        "status": "pending",  # 字段
        "file_id": file_id,  # 字段
        "file_path": str(file_path),  # 字段
        "filename": filename,  # 字段
        "building_type": building_type,  # 字段
        "webhook_url": webhook_url or None,  # 字段
        "created_at": datetime.now().isoformat(),  # 字段
        "updated_at": datetime.now().isoformat(),  # 字段
        "result": None,  # 字段
        "error": None,  # 字段
    }  # code

    # 启动后台任务
    asyncio.create_task(
        _run_review_task(task_id, str(file_path), building_type, webhook_url)
    )  # function call

    return {  # return: dict
        "status": "success",  # 字段
        "task_id": task_id,  # 字段
        "status_url": f"/api/v1/tasks/{task_id}",  # 字段
        "result_url": f"/api/v1/tasks/{task_id}/result",  # 字段
    }  # code


@router.get("/api/v1/tasks/{task_id}", tags=["EMA2"])  # function call
async def get_task_status(
    task_id: str, api_key: str = Depends(_ag.verify_api_key)
):  # function call
    """查询任务状态（EMA2 对接）"""
    task = _ag._tasks.get(task_id)  # function call
    if not task:  # check: negated condition
        raise HTTPException(
            status_code=404,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "TASK_NOT_FOUND",  # 字段
                "message": f"任务不存在: {task_id}",  # 字段
            },
        )  # code

    return {  # return: dict
        "status": "success",  # 字段
        "task_id": task_id,  # 字段
        "state": task["status"],  # 字段
        "filename": task.get("filename"),  # 字段
        "created_at": task.get("created_at"),  # 字段
        "updated_at": task.get("updated_at"),  # 字段
        "error": task.get("error"),  # 字段
    }  # code


@router.get("/api/v1/tasks/{task_id}/result", tags=["EMA2"])  # function call
async def get_task_result(
    task_id: str, api_key: str = Depends(_ag.verify_api_key)
):  # function call
    """获取审查结果（EMA2 对接）"""
    task = _ag._tasks.get(task_id)  # function call
    if not task:  # check: negated condition
        raise HTTPException(
            status_code=404,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "TASK_NOT_FOUND",  # 字段
                "message": f"任务不存在: {task_id}",  # 字段
            },
        )  # code

    # 根据条件判断分支：if task["status"] == "pending"
    if task["status"] == "pending":  # condition: task["status"] == "pending":
        raise HTTPException(
            status_code=409,
            detail={  # 抛出异常
                "status": "pending",  # 字段
                "error_code": "TASK_PENDING",
                "message": "任务仍在处理中，请稍后查询",  # 字段
            },
        )  # code

    # 根据条件判断分支：if task["status"] == "failed"
    if task["status"] == "failed":  # condition: task["status"] == "failed":
        raise HTTPException(
            status_code=500,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "TASK_FAILED",  # 字段
                "message": task.get("error", "任务执行失败"),  # 字段
            },
        )  # code

    return {  # return: dict
        "status": "success",  # 字段
        "task_id": task_id,  # 字段
        "result": task.get("result"),  # 字段
    }  # code


@router.post("/api/v1/webhooks", tags=["EMA2"])  # function call
async def register_webhook(  # code
    url: str = Query(..., description="回调 URL"),  # function call
    events: str = Query("completed", description="触发事件: completed,failed,all"),  # function call
    api_key: str = Depends(_ag.verify_api_key),  # function call
):  # code
    """注册 Webhook 回调（EMA2 对接）

    注册后，当异步审查任务完成或失败时，系统会 POST 通知到该 URL。
    """
    webhook_id = str(uuid.uuid4())[:8]  # function call
    _ag._webhooks[webhook_id] = {  # assignment
        "webhook_id": webhook_id,  # 字段
        "url": url,  # 字段
        "events": events,  # 字段
        "active": True,  # 字段
        "created_at": datetime.now().isoformat(),  # 字段
    }  # code
    return {  # return: dict
        "status": "success",  # 字段
        "webhook_id": webhook_id,  # 字段
        "url": url,  # 字段
        "events": events,  # 字段
    }  # code


@router.get("/api/v1/webhooks", tags=["EMA2"])  # function call
async def list_webhooks(api_key: str = Depends(_ag.verify_api_key)):  # function call
    """查询 Webhook 列表（EMA2 对接）"""
    return {  # return: dict
        "status": "success",  # 字段
        "webhooks": list(_ag._webhooks.values()),  # 字段
    }  # code


@router.delete("/api/v1/webhooks/{webhook_id}", tags=["EMA2"])  # function call
async def delete_webhook(
    webhook_id: str, api_key: str = Depends(_ag.verify_api_key)
):  # function call
    """删除 Webhook（EMA2 对接）"""
    if webhook_id not in _ag._webhooks:  # check: membership test
        raise HTTPException(
            status_code=404,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "WEBHOOK_NOT_FOUND",  # 字段
                "message": f"Webhook 不存在: {webhook_id}",  # 字段
            },
        )  # code
    del _ag._webhooks[webhook_id]  # 删除
    return {"status": "success", "message": "Webhook 已删除"}  # return: dict


# ── P10 反馈闭环 API ───────────────────────────────────────


@router.post("/api/v1/feedbacks", tags=["Feedback"])  # function call
async def submit_feedback(
    body: dict,
    api_key: str = Depends(_ag.verify_api_key),
):  # function call
    """提交违规申诉（P10 反馈闭环）

    用户对审查结果有异议时，提交申诉。
    Body 包含 task_id, clause_id, entity_id, entity_type, reason, description 等。
    申诉数据后续用于模型微调，减少误报。
    """
    record = _ag._feedback_manager.submit(  # assignment
        task_id=body.get("task_id", ""),  # function call
        clause_id=body.get("clause_id", ""),  # function call
        entity_id=body.get("entity_id", ""),  # function call
        entity_type=body.get("entity_type", ""),  # function call
        reason=body.get("reason", ""),  # function call
        description=body.get("description", ""),  # function call
        original_value=body.get("original_value"),  # function call
        severity=body.get("severity", ""),  # function call
    )  # code
    return {"status": "success", "feedback": record}  # return: dict


@router.get("/api/v1/feedbacks", tags=["Feedback"])  # function call
async def list_feedbacks(  # code
    status: str = Query("", description="筛选状态: pending/accepted/rejected"),  # function call
    clause_id: str = Query("", description="筛选规范条款"),  # function call
    limit: int = Query(50, ge=1, le=200),  # function call
    offset: int = Query(0, ge=0),  # function call
    api_key: str = Depends(_ag.verify_api_key),
):  # code
    """查询申诉列表（支持状态和规范条款筛选）"""
    items, total = _ag._feedback_manager.list_all(  # assignment
        status=status, clause_id=clause_id, limit=limit, offset=offset  # assignment
    )  # code
    return {"status": "success", "feedbacks": items, "total": total}  # return: dict


@router.get("/api/v1/feedbacks/stats", tags=["Feedback"])  # function call
async def feedback_stats(api_key: str = Depends(_ag.verify_api_key)):  # function call
    """申诉统计（总数、待处理数、各类分布）"""
    return {"status": "success", "stats": _ag._feedback_manager.stats()}  # return: dict


@router.get("/api/v1/feedbacks/{feedback_id}", tags=["Feedback"])  # function call
async def get_feedback(
    feedback_id: str, api_key: str = Depends(_ag.verify_api_key)
):  # function call
    """查询单条申诉详情"""
    record = _ag._feedback_manager.get(feedback_id)  # function call
    if not record:  # check: negated condition
        raise HTTPException(
            status_code=404,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "FEEDBACK_NOT_FOUND",  # 字段
                "message": f"申诉不存在: {feedback_id}",  # 字段
            },
        )  # code
    return {"status": "success", "feedback": record}  # return: dict


@router.patch("/api/v1/feedbacks/{feedback_id}", tags=["Feedback"])  # function call
async def review_feedback(  # code
    feedback_id: str,  # 操作
    body: dict,  # 操作
    api_key: str = Depends(_ag.verify_api_key),
):  # code
    """审核申诉（P10 反馈闭环）

    管理员审核用户提交的申诉。
    Body: {status: accepted/rejected, reviewed_by, review_comment?}
    """
    record = _ag._feedback_manager.review(  # assignment
        feedback_id,
        body.get("status", ""),
        body.get("reviewed_by", ""),  # 操作
        body.get("review_comment", ""),  # function call
    )  # code
    if not record:  # check: negated condition
        raise HTTPException(
            status_code=404,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "FEEDBACK_NOT_FOUND",  # 字段
                "message": f"申诉不存在: {feedback_id}",  # 字段
            },
        )  # code
    return {"status": "success", "feedback": record}  # return: dict


@router.post("/api/v1/feedbacks/{feedback_id}/adjust", tags=["Feedback"])  # function call
async def adjust_threshold(  # code
    feedback_id: str,  # 操作
    body: dict,  # 操作
    api_key: str = Depends(_ag.verify_api_key),
):  # code
    """基于申诉数据计算/应用阈值调整

    使用 LearningEngine 分析申诉数据，计算建议的阈值调整值。
    如果 apply=true，直接应用调整到规范知识库。
    Body: {clause_id, apply?}
    """
    clause_id = body.get("clause_id", "")  # function call
    apply = body.get("apply", False)  # function call

    # 异常保护：捕获可能失败的调用
    try:  # 尝试
        current, unit, op = _ag._spec_repo.get_threshold(clause_id, "civil")  # 操作
    except ValueError:  # 捕获异常
        raise HTTPException(
            status_code=404,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "CLAUSE_NOT_FOUND",  # 字段
                "message": f"规范不存在: {clause_id}",  # 字段
            },
        )  # code

    adjustment = _ag._learning_engine.compute_adjustment(clause_id, current)  # function call

    # 根据条件判断分支：if apply and adjustment.get("adjustable")
    if apply and adjustment.get("adjustable"):  # check: AND condition
        success = _ag._learning_engine.apply_adjustment(  # assignment
            clause_id,
            adjustment["suggested_threshold"],
            _ag._spec_repo,  # 操作
            reason=f"基于申诉 {feedback_id} 的自动微调",  # assignment
        )  # code
        adjustment["applied"] = success  # 操作

    return {"status": "success", "adjustment": adjustment}  # return: dict


# ── 审查结果对比（Diff） ─────────────────────────────────
