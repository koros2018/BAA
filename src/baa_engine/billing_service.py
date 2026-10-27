"""D4-T3 计费服务：billing cycle 管理 + 结算 + 超额告警。"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 默认单价（元/张图纸）──────────────────────────────────────
DEFAULT_RATE = 5.0  # ¥5 per review


class BillingService:
    """计费周期管理。"""

    def __init__(self, db_session_factory):
        self._db = db_session_factory

    def _session(self):
        return self._db()

    def get_current_cycle(self, key_id: str) -> Optional[dict]:
        """获取 key 当前未结束的 cycle。"""
        from src.baa_engine.db.models.billing import BillingCycle

        with self._session() as s:
            cycle = (
                s.query(BillingCycle)
                .filter(BillingCycle.key_id == key_id)
                .order_by(BillingCycle.start.desc())
                .first()
            )
            if not cycle:
                return None
            return {
                "cycle_id": cycle.cycle_id,
                "key_id": cycle.key_id,
                "start": cycle.start,
                "end": cycle.end,
                "review_count": cycle.review_count,
                "rate": cycle.rate,
                "amount_due": cycle.amount_due,
                "status": cycle.status,
                "paid_at": cycle.paid_at,
            }

    def get_billing_summary(self, key_id: str) -> dict:
        """返回当前 cycle 用量摘要 + 历史付费状态。"""
        from src.baa_engine.db.models.billing import BillingCycle
        from src.baa_engine.license import get_license_manager

        license_mgr = get_license_manager(online=False)
        license_info = license_mgr.validate()

        with self._session() as s:
            cycle = (
                s.query(BillingCycle)
                .filter(BillingCycle.key_id == key_id)
                .order_by(BillingCycle.start.desc())
                .first()
            )
            # 统计当前 cycle 用量
            review_count = cycle.review_count if cycle else 0
            # 从 api_key_usage 表读取累计调用
            try:
                from src.baa_engine.db.models.apikey import ApiKeyUsage

                usage = s.query(ApiKeyUsage).filter_by(key_id=key_id).first()
                total_calls = usage.calls if usage else 0
            except Exception:
                total_calls = 0

        return {
            "key_id": key_id,
            "plan": license_info.plan,
            "trial": license_info.trial,
            "trial_days_remaining": license_mgr.trial_expires_in_days(),
            "cycle": {
                "cycle_id": cycle.cycle_id if cycle else None,
                "start": cycle.start if cycle else None,
                "end": cycle.end if cycle else None,
                "review_count": review_count,
                "rate": cycle.rate if cycle else DEFAULT_RATE,
                "amount_due": cycle.amount_due if cycle else 0.0,
                "status": cycle.status if cycle else "none",
            },
            "limits": {
                "max_monthly_reviews": license_info.max_monthly_reviews,
                "max_concurrent": license_info.max_concurrent,
            },
            "total_calls": total_calls,
        }

    def create_cycle(self, key_id: str, rate: float = DEFAULT_RATE) -> dict:
        """创建新的计费周期。"""
        from src.baa_engine.db.models.billing import BillingCycle

        now = datetime.now(timezone.utc)
        end = now + timedelta(days=30)
        cycle_id = str(uuid.uuid4())

        cycle = BillingCycle(
            cycle_id=cycle_id,
            key_id=key_id,
            start=now.isoformat(),
            end=end.isoformat(),
            rate=rate,
            status="open",
        )

        with self._session() as s:
            s.add(cycle)
            s.commit()
            s.refresh(cycle)

        logger.info(f"[D4-T3] Created billing cycle {cycle_id} for key {key_id}")
        return {
            "cycle_id": cycle.cycle_id,
            "key_id": cycle.key_id,
            "start": cycle.start,
            "end": cycle.end,
            "rate": cycle.rate,
            "status": cycle.status,
        }

    def increment_review_count(self, key_id: str, count: int = 1) -> int:
        """增加当前 cycle 的审查计数。"""
        from src.baa_engine.db.models.billing import BillingCycle

        with self._session() as s:
            cycle = (
                s.query(BillingCycle)
                .filter(BillingCycle.key_id == key_id, BillingCycle.status == "open")
                .order_by(BillingCycle.start.desc())
                .first()
            )
            if not cycle:
                return 0
            cycle.review_count += count
            s.commit()
            return cycle.review_count

    def check_over_limit(self, key_id: str) -> Optional[dict]:
        """检查当前 cycle 是否超额，返回告警信息或 None。"""
        from src.baa_engine.db.models.billing import BillingCycle
        from src.baa_engine.license import get_license_manager

        license_mgr = get_license_manager(online=False)
        info = license_mgr.validate()
        limit = info.max_monthly_reviews

        with self._session() as s:
            cycle = (
                s.query(BillingCycle)
                .filter(BillingCycle.key_id == key_id, BillingCycle.status == "open")
                .order_by(BillingCycle.start.desc())
                .first()
            )
            if not cycle:
                return None
            if cycle.review_count > limit:
                return {
                    "key_id": key_id,
                    "cycle_id": cycle.cycle_id,
                    "review_count": cycle.review_count,
                    "limit": limit,
                    "over_by": cycle.review_count - limit,
                }
        return None

    def mark_paid(self, cycle_id: str, payment_intent_id: str, paid_at: Optional[str] = None) -> bool:
        """标记 cycle 已支付。"""
        from src.baa_engine.db.models.billing import BillingCycle

        ts = paid_at or datetime.now(timezone.utc).isoformat()
        with self._session() as s:
            cycle = s.query(BillingCycle).filter_by(cycle_id=cycle_id).first()
            if not cycle:
                return False
            cycle.status = "paid"
            cycle.paid_at = ts
            cycle.payment_intent_id = payment_intent_id
            s.commit()
            return True

    def finalize_cycle(self, cycle_id: str) -> dict:
        """结束 cycle，计算费用，开启新 cycle。"""
        from src.baa_engine.db.models.billing import BillingCycle

        with self._session() as s:
            cycle = s.query(BillingCycle).filter_by(cycle_id=cycle_id).first()
            if not cycle:
                raise ValueError(f"Cycle {cycle_id} not found")

            # 计算费用
            rate = cycle.rate or DEFAULT_RATE
            cycle.amount_due = cycle.review_count * rate
            cycle.status = "overdue" if cycle.amount_due > 0 else "paid"
            s.commit()

            # 开启新 cycle
            new_cycle = self.create_cycle(cycle.key_id, rate)

        return {
            "closed_cycle": {
                "cycle_id": cycle.cycle_id,
                "review_count": cycle.review_count,
                "amount_due": cycle.amount_due,
                "status": cycle.status,
            },
            "new_cycle": new_cycle,
        }


_service: Optional[BillingService] = None


def get_billing_service():
    global _service
    if _service is None:
        from src.baa_engine.db import get_db_session_factory
        _service = BillingService(get_db_session_factory)
    return _service


def reset_billing_service_for_test():
    global _service
    _service = None
