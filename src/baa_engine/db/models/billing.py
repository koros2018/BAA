"""D4-T3 计费域模型：billing_cycles + billing_alerts（T-C2 用量计量之上构建）。

- billing_cycles：计费周期记录，每 cycle 含 start/end/review_count/rate/amount_due/status
- billing_alerts：计费告警（超额/支付失败/试用到期）
"""
from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text

from .base import Base


class BillingCycle(Base):
    __tablename__ = "billing_cycles"

    cycle_id = Column(String(64), primary_key=True)
    key_id = Column(
        String(64),
        ForeignKey("api_keys.key_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    start = Column(String(40), nullable=False)
    end = Column(String(40), nullable=False)
    review_count = Column(Integer, nullable=False, default=0)
    rate = Column(Float, nullable=False, default=0.0)
    amount_due = Column(Float, nullable=False, default=0.0)
    status = Column(String(20), nullable=False, default="open")
    # open | paid | overdue | cancelled
    paid_at = Column(String(40), nullable=True)
    payment_intent_id = Column(String(200), nullable=True)


class BillingAlert(Base):
    __tablename__ = "billing_alerts"

    alert_id = Column(String(64), primary_key=True)
    key_id = Column(String(64), nullable=False, index=True)
    cycle_id = Column(String(64), nullable=False)
    alert_type = Column(String(50), nullable=False)
    # over_limit | payment_failed | trial_expired | amount_due
    message = Column(Text, nullable=False)
    created_at = Column(String(40), nullable=False)
