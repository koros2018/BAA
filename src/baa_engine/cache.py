"""
BAA 持久化缓存模块（T-C1 统一数据层）
===================
基于统一数据层（SQLAlchemy engine）的持久化缓存。

设计目标：
1. 服务重启后缓存不丢失
2. 自动清理过期条目（TTL）
3. 支持多级缓存（文件哈希 → 解析结果 / 审查结果）
4. 多副本共享存储可用（BAA_DATABASE_URL → PostgreSQL；回退 SQLite WAL）

T-C1 变更：线程局部 sqlite3 连接 → 统一 engine 连接池；
engine 惰性创建（__init__ 不建连接，--preload fork 安全）。
"""

import json  # JSON serialization
import logging  # logging framework
import os  # filesystem operations
import threading  # singleton lock
import time  # time/timestamp operations
from typing import Any, Callable, Dict, Optional

from sqlalchemy import delete, func, select, update

from src.baa_engine.db import (
    ensure_schema,
    get_session_factory,
    resolve_database_url,
)
from src.baa_engine.db.models.cache import CacheEntry

logger = logging.getLogger(__name__)  # module-level logger

# ── 默认缓存路径（legacy 位置，仅作迁移工具数据源与显式参数默认值） ──
DEFAULT_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache"
)  # cache data directory path
DEFAULT_DB_PATH = os.path.join(DEFAULT_CACHE_DIR, "baa_cache.db")  # legacy SQLite file path

# ── 默认 TTL（秒） ───────────────────────────────────────
CACHE_TTL = {  # default TTL per cache type
    "drawing_parse": 86400 * 7,  # 7 天
    "review_result": 86400 * 3,  # 3 天
    "semantic_analysis": 86400 * 7,  # 7 天
}  # TTL dict end

# ── 最大条目数限制（防止缓存表膨胀） ────────────────────
MAX_ENTRIES_PER_TYPE = {  # max entries per cache type
    "drawing_parse": 500,  # drawing parse cache limit
    "review_result": 500,  # review result cache limit
    "semantic_analysis": 500,  # semantic analysis cache limit
}  # max entries dict end


class PersistentCache:  # persistent cache on unified data layer
    """持久化缓存（统一 engine，线程安全）"""

    _instance = None  # singleton instance reference
    _lock = threading.Lock()  # singleton initialization lock

    def __new__(cls, db_path: str = DEFAULT_DB_PATH):  # override to enforce singleton
        """实现单例模式。"""
        with cls._lock:  # critical section for singleton init
            if cls._instance is None:  # create instance if not yet created
                cls._instance = super().__new__(cls)  # allocate new class instance
                cls._instance._initialized = False  # flag indicating not initialized
        return cls._instance  # return singleton instance

    def __init__(self, db_path: str = DEFAULT_DB_PATH):  # initialize cache (no engine here)
        """初始化实例。engine 惰性创建：import/单例化时不建任何连接（fork 安全）。"""
        if self._initialized:  # skip if already initialized
            return  # early return
        self._initialized = True  # mark as initialized
        self._db_path = db_path  # store database file path
        # 显式路径（测试隔离）→ 独立 SQLite；默认路径 → 统一 URL 解析
        if os.path.abspath(db_path) == os.path.abspath(DEFAULT_DB_PATH):
            self._url = resolve_database_url()
        else:
            self._url = f"sqlite:///{db_path}"

    def _sf(self):  # lazy session factory with schema fallback
        """获取会话工厂（首次使用时建 engine + 幂等建表）。"""
        ensure_schema(self._url)  # 生产以 Alembic 为准，此处兜底（幂等）
        return get_session_factory(self._url)

    def get(self, cache_key: str, cache_type: str = "review_result") -> Optional[Any]:
        """获取缓存值，未命中或过期返回 None"""
        try:  # try block for cache retrieval
            sf = self._sf()  # lazy session factory
            session = sf()
            try:
                now = time.time()  # current timestamp for expiry check
                # 概率性清理过期条目（降低清理频率）
                if hash(cache_key) % 100 < 5:  # 5% 概率
                    self._cleanup_expired()  # probabilistic expired cleanup

                row = session.execute(
                    select(CacheEntry.value, CacheEntry.expires_at).where(
                        CacheEntry.cache_key == cache_key,
                        CacheEntry.cache_type == cache_type,
                    )
                ).first()  # fetch first matching row

                if row is None:  # no row found = cache miss
                    return None  # return None for miss

                if row.expires_at < now:  # check if entry has expired
                    # 过期条目，延迟删除
                    session.execute(
                        delete(CacheEntry).where(CacheEntry.cache_key == cache_key)
                    )
                    session.commit()  # commit deletion
                    return None  # treat expired as miss

                # 更新访问计数
                session.execute(
                    update(CacheEntry)
                    .where(CacheEntry.cache_key == cache_key)
                    .values(access_count=CacheEntry.access_count + 1, last_access_at=now)
                )
                session.commit()  # commit metadata update

                return json.loads(row.value)  # deserialize and return cached value
            finally:
                sf.remove()
        except Exception as e:  # catch any database error
            logger.warning(f"缓存读取失败: {e}")  # log warning for read failure
            return None  # return None on error

    def set(
        self,
        cache_key: str,
        value: Any,
        cache_type: str = "review_result",  # write value to cache
        ttl: Optional[int] = None,
    ) -> None:  # optional TTL override
        """写入缓存"""
        try:  # try block for cache write
            if ttl is None:  # check if TTL not provided
                ttl = CACHE_TTL.get(cache_type, 86400)  # use default TTL for this type

            now = time.time()  # current timestamp
            serialized = json.dumps(
                value, ensure_ascii=False, default=str
            )  # serialize value to JSON string

            sf = self._sf()  # lazy session factory
            session = sf()
            try:
                # 与旧 INSERT OR REPLACE 语义一致：同 PK 覆盖
                session.merge(
                    CacheEntry(
                        cache_key=cache_key,
                        cache_type=cache_type,
                        value=serialized,
                        created_at=now,
                        expires_at=now + ttl,
                        access_count=0,
                        last_access_at=now,
                    )
                )

                max_entries = MAX_ENTRIES_PER_TYPE.get(cache_type, 500)
                count = session.scalar(
                    select(func.count()).select_from(CacheEntry).where(
                        CacheEntry.cache_type == cache_type
                    )
                )

                if (count or 0) > max_entries:
                    keep = session.scalars(
                        select(CacheEntry.cache_key)
                        .where(CacheEntry.cache_type == cache_type)
                        .order_by(CacheEntry.last_access_at.desc())
                        .limit(max_entries)
                    ).all()
                    session.execute(
                        delete(CacheEntry).where(
                            CacheEntry.cache_type == cache_type,
                            CacheEntry.cache_key.notin_(keep),
                        )
                    )

                session.commit()
            finally:
                sf.remove()
        except Exception as e:
            logger.warning(f"缓存写入失败: {e}")

    def delete(self, cache_key: str) -> None:
        """删除指定缓存"""
        try:  # try block for deletion
            sf = self._sf()
            session = sf()
            try:
                session.execute(delete(CacheEntry).where(CacheEntry.cache_key == cache_key))
                session.commit()
            finally:
                sf.remove()
        except Exception as e:  # catch any database error
            logger.warning(f"缓存删除失败: {e}")  # log warning for delete failure

    def delete_by_type(self, cache_type: str) -> int:  # delete all entries of a type
        """删除指定类型的所有缓存，返回删除条数"""
        try:  # try block for bulk deletion
            sf = self._sf()
            session = sf()
            try:
                result = session.execute(
                    delete(CacheEntry).where(CacheEntry.cache_type == cache_type)
                )
                session.commit()
                return result.rowcount or 0
            finally:
                sf.remove()
        except Exception as e:  # catch any database error
            logger.warning(f"缓存清理失败: {e}")  # log warning for cleanup failure
            return 0  # return 0 on error

    def clear(self) -> None:  # clear all cache entries
        """清空所有缓存"""
        try:  # try block for full cleanup
            sf = self._sf()
            session = sf()
            try:
                session.execute(delete(CacheEntry))
                session.commit()
            finally:
                sf.remove()
        except Exception as e:  # catch any database error
            logger.warning(f"缓存清空失败: {e}")  # log warning for clear failure

    def stats(self) -> Dict[str, Any]:  # get cache statistics
        """缓存统计"""
        try:  # try block for stats query
            sf = self._sf()
            session = sf()
            try:
                total = session.scalar(select(func.count()).select_from(CacheEntry)) or 0
                expired = (
                    session.scalar(
                        select(func.count())
                        .select_from(CacheEntry)
                        .where(CacheEntry.expires_at < time.time())
                    )
                    or 0
                )
                by_type = session.execute(
                    select(CacheEntry.cache_type, func.count()).group_by(CacheEntry.cache_type)
                ).all()
                return {
                    "total": total,
                    "expired": expired,
                    "active": total - expired,
                    "by_type": {t: c for t, c in by_type},
                }
            finally:
                sf.remove()
        except Exception as e:  # catch any database error
            return {"error": str(e)}  # return error message dict

    def _cleanup_expired(self) -> int:  # cleanup expired entries
        """清理过期条目，返回清理条数"""
        try:  # try block for cleanup
            sf = self._sf()
            session = sf()
            try:
                result = session.execute(
                    delete(CacheEntry).where(CacheEntry.expires_at < time.time())
                )
                session.commit()
                return result.rowcount or 0
            finally:
                sf.remove()
        except Exception:  # catch any database error
            return 0  # return 0 on error

    def get_or_compute(
        self,
        cache_key: str,
        compute_fn: Callable,  # cache-aside with auto-fill
        cache_type: str = "review_result",
        ttl: Optional[int] = None,
    ) -> Any:  # optional TTL override
        """缓存穿透保护：先查缓存，未命中则计算并缓存"""
        cached = self.get(cache_key, cache_type)  # try cache first
        if cached is not None:  # check if cache hit
            return cached  # return cached value

        result = compute_fn()  # compute value on miss
        if result is not None:  # check computed result not None
            self.set(cache_key, result, cache_type, ttl)  # cache computed result
        return result  # return computed value

    def close(self):  # close cache backend
        """释放该缓存实例使用的 engine（测试清理/关停用）"""
        from src.baa_engine.db import dispose_engine

        dispose_engine(self._url)


# ── 便捷函数 ──────────────────────────────────────────────


def make_cache_key(
    file_hash: str, standard: str = "GB50016", building_type: str = "civil"
) -> str:  # generate review result cache key
    """生成审查结果缓存键"""
    return f"{file_hash}:{standard}:{building_type}"  # return formatted key string


def make_drawing_cache_key(file_hash: str) -> str:  # generate drawing parse cache key
    """生成图纸解析缓存键"""
    return f"drawing:{file_hash}"  # return drawing cache key


def make_semantic_cache_key(primitives_hash: str) -> str:  # generate semantic analysis cache key
    """生成语义分析缓存键"""
    return f"semantic:{primitives_hash}"  # return semantic cache key


# ── 全局单例 ──────────────────────────────────────────────
_cache: Optional[PersistentCache] = None  # global cache singleton variable


def get_cache() -> PersistentCache:  # get or create global cache instance
    """获取全局缓存实例（惰性：不建 engine，仅实例化单例）"""
    global _cache  # modify module-level global
    if _cache is None:  # check singleton not created
        _cache = PersistentCache()  # create new PersistentCache instance
    return _cache  # return global cache instance
