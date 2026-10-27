"""D3-T2 整改通知单 / 复查意见 API 端点。"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from src.api.review.review_routes import verify_api_key
from src.baa_engine.word_generator import build_correction_notice_docx, build_recheck_opinion_docx

router = APIRouter(tags=["Corrections"])


@router.post("/api/v1/corrections/{review_id}/notice")
async def generate_notice(review_id: str, api_key: str = Depends(verify_api_key)):
    """生成整改通知单 .docx 并下载。"""
    from src.api.review.review_history import get_review_detail

    detail = get_review_detail(review_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Review {review_id} not found")

    # 仅取 confirmed 的违规条目
    confirmed = [
        d for d in detail.get("details", [])
        if d.get("audit", {}).get("status") == "confirmed"
    ]
    if not confirmed:
        raise HTTPException(status_code=400, detail="No confirmed findings for this review")

    meta = {
        "project_name": detail.get("project_name", ""),
        "drawing_name": detail.get("drawingName", ""),
        "reviewer": detail.get("reviewer", "系统"),
        "corrector": detail.get("corrector", ""),
        "deadline": detail.get("deadline", ""),
    }
    path = build_correction_notice_docx(confirmed, meta)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.split("/")[-1],
    )


@router.post("/api/v1/corrections/{review_id}/recheck")
async def generate_recheck(review_id: str, api_key: str = Depends(verify_api_key)):
    """生成复查意见 .docx 并下载。"""
    from src.api.review.review_history import get_review_detail

    detail = get_review_detail(review_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Review {review_id} not found")

    rechecks = detail.get("rechecks", [])
    if not rechecks:
        # 从 corrections 推导复查状态
        rechecks = []
        for c in detail.get("corrections", []):
            rechecks.append({
                "function_id": c.get("function_id", ""),
                "entity_id": c.get("entity_id", ""),
                "status": c.get("recheck_status", "pending"),
                "opinion": c.get("recheck_opinion", "—"),
            })

    if not rechecks:
        raise HTTPException(status_code=400, detail="No recheck data for this review")

    meta = {
        "project_name": detail.get("project_name", ""),
        "drawing_name": detail.get("drawingName", ""),
        "reviewer": detail.get("reviewer", "系统"),
        "corrector": detail.get("corrector", ""),
    }
    path = build_recheck_opinion_docx(rechecks, meta)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.split("/")[-1],
    )
