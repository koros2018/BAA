"""D4-T3 计费测试：BillingService + billing cycles + 超额检测。"""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_services():
    from src.baa_engine.billing_service import reset_billing_service_for_test
    from src.baa_engine.license import reset_license_manager_for_test

    reset_billing_service_for_test()
    reset_license_manager_for_test()
    yield
    reset_billing_service_for_test()
    reset_license_manager_for_test()


def _setup_db(tmp_path: Path):
    """初始化 SQLite 数据库，创建 billing 相关表。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    from src.baa_engine.db.models.base import Base
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session


def test_billing_service_create_cycle(tmp_path):
    """创建计费周期。"""
    from src.baa_engine.billing_service import BillingService

    Session = _setup_db(tmp_path)
    svc = BillingService(Session)
    result = svc.create_cycle("key-001")
    assert result["key_id"] == "key-001"
    assert result["status"] == "open"
    assert result["rate"] > 0


def test_billing_service_increment_review_count(tmp_path):
    """增加审查计数。"""
    from src.baa_engine.billing_service import BillingService

    Session = _setup_db(tmp_path)
    svc = BillingService(Session)
    svc.create_cycle("key-002")
    count = svc.increment_review_count("key-002", 3)
    assert count == 3


def test_billing_service_get_summary(tmp_path):
    """获取用量摘要。"""
    from src.baa_engine.billing_service import BillingService

    Session = _setup_db(tmp_path)
    svc = BillingService(Session)
    svc.create_cycle("key-003")
    summary = svc.get_billing_summary("key-003")
    assert summary["key_id"] == "key-003"
    assert summary["plan"] == "free"
    assert "cycle" in summary


def test_billing_service_mark_paid(tmp_path):
    """标记已支付。"""
    from src.baa_engine.billing_service import BillingService

    Session = _setup_db(tmp_path)
    svc = BillingService(Session)
    cycle = svc.create_cycle("key-004")
    ok = svc.mark_paid(cycle["cycle_id"], "stripe-session-123")
    assert ok is True

    summary = svc.get_billing_summary("key-004")
    assert summary["cycle"]["status"] == "paid"


def test_billing_service_finalize_cycle(tmp_path):
    """结束 cycle，开启新 cycle。"""
    from src.baa_engine.billing_service import BillingService

    Session = _setup_db(tmp_path)
    svc = BillingService(Session)
    cycle = svc.create_cycle("key-005")
    svc.increment_review_count("key-005", 10)

    result = svc.finalize_cycle(cycle["cycle_id"])
    assert result["closed_cycle"]["status"] in ("paid", "overdue")
    assert result["new_cycle"]["status"] == "open"
