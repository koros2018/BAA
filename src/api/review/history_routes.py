"""
审查历史记录 — 持久化查询端点

所有端点都是 review_history.py 持久化层的薄壳代理，无需访问引擎。
"""

from fastapi import Depends, HTTPException, Query
from . import (
    _get_rq,
    verify_api_key,
)

# ── 导入公共 router ────────────────────────────────────────
from . import router


@router.get("/review/history")  # 审查历史列表
async def list_review_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    drawing_name: str = Query(None, description="图纸名称搜索"),
    building_type: str = Query(None, description="建筑类型筛选"),
    api_key: str = Depends(verify_api_key),
):
    """查询审查历史记录列表（分页）"""
    from .review_history import list_review_history as _list

    return _list(limit=limit, offset=offset, drawing_name=drawing_name, building_type=building_type)


@router.get("/review/history/{review_id}")  # 审查历史详情
def get_review_detail(
    review_id: str,
    api_key: str = Depends(verify_api_key),
):
    """获取单条审查记录完整详情"""
    from .review_history import get_review_detail as _get

    result = _get(review_id)
    if result is None:
        raise HTTPException(status_code=404, detail="审查记录不存在")
    return result


@router.delete("/review/history/{review_id}")  # 删除审查历史
def delete_review_history(
    review_id: str,
    api_key: str = Depends(verify_api_key),
):
    """删除单条审查记录"""
    from .review_history import delete_review_history as _del

    ok = _del(review_id)
    if not ok:
        raise HTTPException(status_code=404, detail="审查记录不存在")
    return {"status": "success", "message": "已删除"}


@router.delete("/review/history")  # 清空审查历史
def clear_review_history(
    api_key: str = Depends(verify_api_key),
):
    """清空所有审查历史记录"""
    from .review_history import clear_review_history as _clear

    count = _clear()
    return {"status": "success", "deleted": count, "message": f"已清空 {count} 条记录"}


@router.delete("/review/queue/{task_id}")  # 取消审查任务
async def review_queue_cancel(
    task_id: str,
    api_key: str = Depends(verify_api_key),
):
    """取消排队中的审查任务

    仅能取消排队中（status=queued）的任务。
    已在运行或已完成的任务无法取消。
    """
    cancelled = _get_rq().cancel(task_id)
    if not cancelled:
        status_info = _get_rq().get_status(task_id)
        if status_info is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "status": "error",
                    "error_code": "TASK_NOT_FOUND",
                    "message": f"任务不存在: {task_id}",
                },
            )
        raise HTTPException(
            status_code=409,
            detail={
                "status": "error",
                "error_code": "TASK_CANT_CANCEL",
                "message": f"任务当前状态为 {status_info['status']}，无法取消",
            },
        )
    return {"status": "success", "message": f"任务 {task_id} 已取消"}
