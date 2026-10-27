"""D4-T3 计费路由：billing cycles + payment webhooks."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.review.review_routes import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Billing"])


# ── Pydantic schemas ──────────────────────────────────────────

class BillingSummaryResponse(BaseModel):
    key_id: str
    plan: str
    trial: bool
    trial_days_remaining: int
    cycle: dict
    limits: dict
    total_calls: int


# ── Endpoints ─────────────────────────────────────────────────

@router.get("/api/v1/billing/summary", response_model=BillingSummaryResponse)
async def get_billing_summary(api_key: str = Depends(verify_api_key)):
    """查询当前计费周期用量摘要（D4-T3）。"""
    from src.baa_engine.billing_service import get_billing_service

    svc = get_billing_service()
    summary = svc.get_billing_summary(api_key)
    return BillingSummaryResponse(**summary)


@router.post("/api/v1/billing/cycles", tags=["Billing-Admin"])
async def create_billing_cycle(api_key: str = Depends(verify_api_key)):
    """创建新计费周期（管理端，D4-T3）。"""
    from src.baa_engine.billing_service import get_billing_service

    svc = get_billing_service()
    result = svc.create_cycle(api_key)
    return result


@router.post("/api/v1/billing/cycles/{cycle_id}/increment")
async def increment_review_count(
    cycle_id: str,
    count: int = Query(default=1, ge=1),
    api_key: str = Depends(verify_api_key),
):
    """增加审查计数（内部用）。"""
    from src.baa_engine.billing_service import get_billing_service

    svc = get_billing_service()
    new_count = svc.increment_review_count(api_key, count)
    return {"key_id": api_key, "review_count": new_count}


@router.get("/api/v1/billing/alerts/over-limit")
async def check_over_limit(api_key: str = Depends(verify_api_key)):
    """检查是否超额。"""
    from src.baa_engine.billing_service import get_billing_service

    svc = get_billing_service()
    alert = svc.check_over_limit(api_key)
    if alert:
        return {"over_limit": True, **alert}
    return {"over_limit": False}


# ── Payment webhooks ──────────────────────────────────────────

@router.post("/api/v1/payments/stripe/webhook")
async def stripe_webhook(request_body: bytes):
    """Stripe 支付回调（D4-T3）。"""
    import hashlib
    import hmac

    from src.baa_engine.billing_service import get_billing_service

    sig_header = request_body.decode()  # 实际应读取 headers["stripe-signature"]
    webhook_secret = ""  # TODO: BAA_STRIPE_WEBHOOK_SECRET

    # 简化实现：直接解析 body
    import json
    try:
        event = json.loads(request_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    svc = get_billing_service()

    if event.get("type") == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        metadata = session.get("metadata", {})
        cycle_id = metadata.get("cycle_id")
        if not cycle_id:
            logger.warning("[D4-T3] Stripe webhook missing cycle_id")
            raise HTTPException(status_code=400, detail="Missing cycle_id")
        svc.mark_paid(cycle_id, session.get("id"))
        logger.info(f"[D4-T3] Stripe payment completed for cycle {cycle_id}")
        return {"status": "ok"}

    return {"status": "ignored"}


@router.post("/api/v1/payments/wechat/webhook")
async def wechat_webhook(request_body: dict):
    """微信支付回调（D4-T3）。"""
    from src.baa_engine.billing_service import get_billing_service

    svc = get_billing_service()

    # 微信支付回调格式简化
    out_trade_no = request_body.get("out_trade_no", "")
    transaction_id = request_body.get("transaction_id", "")

    # out_trade_no 通常包含 cycle_id
    cycle_id = out_trade_no.replace("baa_cycle_", "") if out_trade_no.startswith("baa_cycle_") else out_trade_no

    if cycle_id:
        svc.mark_paid(cycle_id, transaction_id)
        logger.info(f"[D4-T3] WeChat payment completed for cycle {cycle_id}")

    return {"return_code": "SUCCESS", "return_msg": "OK"}
