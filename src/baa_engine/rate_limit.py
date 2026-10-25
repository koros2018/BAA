"""T-C2 分布式限流：基于统一数据库的固定窗口计数器。

多副本一致性由存储层原子语义保证，而非进程内 dict：
- PostgreSQL：`INSERT ... ON CONFLICT DO UPDATE ... WHERE count < limit RETURNING count`，
  单条语句完成「判定 + 计数」，并发下不会超发
- SQLite：`INSERT ... ON CONFLICT DO NOTHING` + 条件 `UPDATE ... WHERE count < limit`
  （语句级写锁串行化，同样不会超发）

计数行按窗口过期（expires_at），后台不常驻，每 N 次调用惰性清理一次。
未配置数据库时（统一层默认 SQLite）同样工作，只是共享范围限于同库文件。
"""

import logging
import os
import threading
import time
from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db import ensure_schema, get_engine, resolve_database_url
from .db.models.ratelimit import RateLimitBucket

logger = logging.getLogger(__name__)

_TABLE = RateLimitBucket.__table__

# 每 N 次调用触发一次过期行清理（避免每请求都 DELETE）
_CLEANUP_EVERY = 200


@dataclass
class RateLimitResult:
    """限流判定结果。"""

    allowed: bool
    limit: int
    remaining: int
    retry_after: int  # 秒；仅 allowed=False 时有意义
    bucket_key: str


class DistributedRateLimiter:
    """跨副本共享的固定窗口限流器（线程安全，无进程内状态）。"""

    def __init__(self, url: str = None, window: float = 60.0):
        self._url = resolve_database_url(url)
        self._window = float(window)
        self._cleanup_lock = threading.Lock()
        self._calls = 0

    # ── 内部 ──────────────────────────────────────────

    def _is_sqlite(self) -> bool:
        return self._url.strip().lower().startswith("sqlite")

    def _maybe_cleanup(self, now: float) -> None:
        """每 N 次调用清理一次过期窗口（带进程内计数，开销可忽略）。"""
        with self._cleanup_lock:
            self._calls += 1
            if self._calls % _CLEANUP_EVERY != 0:
                return
        try:
            engine = get_engine(self._url)
            with engine.begin() as conn:
                conn.execute(delete(_TABLE).where(_TABLE.c.expires_at < now))
        except Exception as e:  # 清理失败不影响限流主链路
            logger.warning("[RateLimit] 过期窗口清理失败: %s", e)

    def _pg_consume(self, bucket_key, window_start, expires_at, limit) -> int:
        """PG 原子消费；返回消费后的计数，未消费返回 -1。"""
        stmt = (
            pg_insert(_TABLE)
            .values(
                bucket_key=bucket_key,
                window_start=window_start,
                count=1,
                expires_at=expires_at,
            )
            .on_conflict_do_update(
                index_elements=[_TABLE.c.bucket_key],
                set_={"count": _TABLE.c.count + 1},
                where=_TABLE.c.count < limit,
            )
            .returning(_TABLE.c.count)
        )
        engine = get_engine(self._url)
        with engine.begin() as conn:
            row = conn.execute(stmt).first()
        return int(row[0]) if row is not None else -1

    def _sqlite_consume(self, bucket_key, window_start, expires_at, limit) -> int:
        """SQLite 原子消费：先尝试插入，冲突则条件自增。"""
        engine = get_engine(self._url)
        with engine.begin() as conn:
            ins = (
                sqlite_insert(_TABLE)
                .values(
                    bucket_key=bucket_key,
                    window_start=window_start,
                    count=1,
                    expires_at=expires_at,
                )
                .on_conflict_do_nothing(index_elements=["bucket_key"])
            )
            if conn.execute(ins).rowcount == 1:
                return 1
            upd = (
                update(_TABLE)
                .where(
                    _TABLE.c.bucket_key == bucket_key,
                    _TABLE.c.count < limit,
                )
                .values(count=_TABLE.c.count + 1)
            )
            if conn.execute(upd).rowcount == 1:
                return int(
                    conn.execute(
                        select(_TABLE.c.count).where(_TABLE.c.bucket_key == bucket_key)
                    ).scalar()
                )
            return -1

    # ── 公开 API ─────────────────────────────────────

    def check_and_consume(self, subject: str, limit: int, window: float = None) -> RateLimitResult:
        """判定并消费一次配额。

        Args:
            subject: 限流主体（如 key:<key_id>、ip:<addr>）
            limit: 窗口内允许次数（<=0 表示不限流）
            window: 窗口秒数，默认 60

        Returns:
            RateLimitResult；allowed=False 时 retry_after 为建议等待秒数
        """
        win = float(window or self._window)
        now = time.time()
        window_start = int(now // win) * int(win)
        bucket_key = f"{subject}:{window_start}"
        expires_at = window_start + int(win) * 2  # 留一个窗口余量便于排障

        if limit <= 0:
            return RateLimitResult(True, limit, 10**9, 0, bucket_key)

        ensure_schema(self._url)  # 首启兜底（生产由 Alembic 建表）
        try:
            count = (
                self._sqlite_consume(bucket_key, window_start, expires_at, limit)
                if self._is_sqlite()
                else self._pg_consume(bucket_key, window_start, expires_at, limit)
            )
        except Exception as e:
            # 存储不可用时不阻断请求（fail-open），但记录告警
            logger.warning("[RateLimit] 计数失败，放行请求: %s", e)
            return RateLimitResult(True, limit, limit, 0, bucket_key)

        self._maybe_cleanup(now)
        if count < 0:
            retry_after = max(1, int(window_start + win - now))
            return RateLimitResult(False, limit, 0, retry_after, bucket_key)
        return RateLimitResult(True, limit, max(0, limit - count), 0, bucket_key)

    def peek(self, subject: str, window: float = None) -> int:
        """查询当前窗口已消费次数（排障/测试用）。"""
        win = float(window or self._window)
        window_start = int(time.time() // win) * int(win)
        bucket_key = f"{subject}:{window_start}"
        engine = get_engine(self._url)
        with engine.connect() as conn:
            val = conn.execute(
                select(_TABLE.c.count).where(_TABLE.c.bucket_key == bucket_key)
            ).scalar()
        return int(val or 0)

    def reset(self, subject: str = None) -> None:
        """清空计数（测试用；subject 为空则清空全部）。"""
        ensure_schema(self._url)
        engine = get_engine(self._url)
        with engine.begin() as conn:
            stmt = delete(_TABLE)
            if subject:
                stmt = stmt.where(_TABLE.c.bucket_key.like(f"{subject}:%"))
            conn.execute(stmt)


# ── 单例 ──────────────────────────────────────────────

_limiter = None
_limiter_lock = threading.Lock()


def get_rate_limiter() -> DistributedRateLimiter:
    """获取全局限流器（首次调用时才解析 URL / 建连接，fork 安全）。"""
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                _limiter = DistributedRateLimiter()
    return _limiter


def rate_limit_enabled() -> bool:
    """开关：BAA_RATE_LIMIT_ENABLED=0 可整体关闭（默认开启）。"""
    return os.getenv("BAA_RATE_LIMIT_ENABLED", "1").strip().lower() not in ("0", "false", "no")
