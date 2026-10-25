"""T-C2 分布式限流单测（SQLite 统一库；PG 多进程一致性见 test_pg_cluster）。"""

import os

import pytest

from src.baa_engine.db import dispose_engine
from src.baa_engine.rate_limit import DistributedRateLimiter, rate_limit_enabled


@pytest.fixture()
def limiter(tmp_path):
    url = f"sqlite:///{(tmp_path / 'rl.db').as_posix()}"
    lim = DistributedRateLimiter(url=url, window=60.0)
    yield lim
    lim.reset()
    dispose_engine(url)


def test_limit_exact_boundary(limiter):
    """窗口内恰好放行 limit 次，第 limit+1 次拒绝。"""
    subject = "key:test-boundary"
    limit = 5
    allowed = [limiter.check_and_consume(subject, limit).allowed for _ in range(limit)]
    assert allowed == [True] * limit
    rejected = limiter.check_and_consume(subject, limit)
    assert rejected.allowed is False
    assert rejected.remaining == 0
    assert 1 <= rejected.retry_after <= 60
    assert limiter.peek(subject) == limit  # 拒绝不额外计数


def test_subjects_are_isolated(limiter):
    """不同主体互不挤占配额。"""
    for _ in range(3):
        assert limiter.check_and_consume("key:a", 3).allowed
    assert limiter.check_and_consume("key:a", 3).allowed is False
    assert limiter.check_and_consume("key:b", 3).allowed is True


def test_window_rollover(limiter):
    """跨窗口后配额重置（用 1 秒窗口实测滚动）。"""
    subject = "key:rollover"
    assert limiter.check_and_consume(subject, 1, window=1).allowed
    assert limiter.check_and_consume(subject, 1, window=1).allowed is False
    import time

    time.sleep(1.1)
    assert limiter.check_and_consume(subject, 1, window=1).allowed is True


def test_unlimited_when_limit_non_positive(limiter):
    """limit<=0 表示不限流。"""
    for _ in range(10):
        assert limiter.check_and_consume("key:free", 0).allowed


def test_reset(limiter):
    subject = "key:reset"
    limiter.check_and_consume(subject, 1)
    assert limiter.check_and_consume(subject, 1).allowed is False
    limiter.reset(subject)
    assert limiter.check_and_consume(subject, 1).allowed is True


def test_enabled_switch(monkeypatch):
    """BAA_RATE_LIMIT_ENABLED=0 可整体关闭。"""
    assert rate_limit_enabled() is True
    monkeypatch.setenv("BAA_RATE_LIMIT_ENABLED", "0")
    assert rate_limit_enabled() is False


def test_same_db_shared_across_instances(tmp_path):
    """同一库上的两个限流器实例共享计数（模拟多副本的最小场景）。"""
    url = f"sqlite:///{(tmp_path / 'shared.db').as_posix()}"
    a = DistributedRateLimiter(url=url)
    b = DistributedRateLimiter(url=url)
    subject = "key:shared"
    assert a.check_and_consume(subject, 2).allowed is True
    assert b.check_and_consume(subject, 2).allowed is True
    assert a.check_and_consume(subject, 2).allowed is False
    a.reset()
    dispose_engine(url)
