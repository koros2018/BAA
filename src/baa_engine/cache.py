"""
BAA 持久化缓存模块
===================
基于 SQLite 的持久化缓存，替代/补充现有内存缓存。

设计目标：
1. 服务重启后缓存不丢失
2. 自动清理过期条目（TTL）
3. 支持多级缓存（文件哈希 → 解析结果 / 审查结果）
4. 线程安全（SQLite WAL 模式）
"""
import json  # JSON serialization
import sqlite3  # SQLite database API
import threading  # thread safety primitives
import time  # time/timestamp operations
import hashlib  # MD5 hashing for cache keys
import os  # filesystem operations
import logging  # logging framework
from pathlib import Path  # path utilities
from typing import Any, Optional, Dict, Callable  # generic type hints

logger = logging.getLogger(__name__)  # module-level logger

# ── 默认缓存路径 ──────────────────────────────────────────
DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")  # cache data directory path
DEFAULT_DB_PATH = os.path.join(DEFAULT_CACHE_DIR, "baa_cache.db")  # SQLite database file path

# ── 默认 TTL（秒） ───────────────────────────────────────
CACHE_TTL = {  # default TTL per cache type
    "drawing_parse": 86400 * 7,    # 7 天
    "review_result": 86400 * 3,     # 3 天
    "semantic_analysis": 86400 * 7, # 7 天
}  # TTL dict end

# ── 最大条目数限制（防止 SQLite 膨胀） ────────────────────
MAX_ENTRIES_PER_TYPE = {  # max entries per cache type
    "drawing_parse": 500,  # drawing parse cache limit
    "review_result": 500,  # review result cache limit
    "semantic_analysis": 500,  # semantic analysis cache limit
}  # max entries dict end


class PersistentCache:  # persistent cache with SQLite backend
    """基于 SQLite 的持久化缓存，线程安全"""

    _instance = None  # singleton instance reference
    _lock = threading.Lock()  # singleton initialization lock

    def __new__(cls, db_path: str = DEFAULT_DB_PATH):  # override to enforce singleton
        with cls._lock:  # critical section for singleton init
            if cls._instance is None:  # create instance if not yet created
                cls._instance = super().__new__(cls)  # allocate new class instance
                cls._instance._initialized = False  # flag indicating not initialized
        return cls._instance  # return singleton instance

    def __init__(self, db_path: str = DEFAULT_DB_PATH):  # initialize cache database
        if self._initialized:  # skip if already initialized
            return  # early return
        self._initialized = True  # mark as initialized
        self._db_path = db_path  # store database file path
        self._local = threading.local()  # thread-local storage for connections
        self._write_lock = threading.Lock()  # lock for exclusive writes

        # 确保目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)  # ensure cache directory exists

        # 初始化表
        self._init_db()  # initialize database schema

    def _get_conn(self) -> sqlite3.Connection:  # get thread-local SQLite connection
        """获取当前线程的数据库连接（惰性创建）"""
        if not hasattr(self._local, "conn") or self._local.conn is None:  # lazy connection creation check
            conn = sqlite3.connect(self._db_path, timeout=10)  # open SQLite connection
            conn.execute("PRAGMA journal_mode=WAL")  # WAL mode for concurrent reads
            conn.execute("PRAGMA synchronous=NORMAL")  # NORMAL sync for balanced perf
            conn.execute("PRAGMA cache_size=-8000")  # 8MB
            conn.row_factory = sqlite3.Row  # enable row dict access
            self._local.conn = conn  # store connection in thread-local
        return self._local.conn  # return connection object

    def _init_db(self):  # initialize database schema
        """创建表结构"""
        conn = self._get_conn()  # get thread-local connection
        # SQL: create cache_entries table DDL
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_entries (  # table definition start
                cache_key TEXT PRIMARY KEY,  # column: unique cache key
                cache_type TEXT NOT NULL,  # column: cache type classification
                value TEXT NOT NULL,  # column: serialized JSON value
                created_at REAL NOT NULL,  # column: creation timestamp
                expires_at REAL NOT NULL,  # column: expiration timestamp
                access_count INTEGER DEFAULT 0,  # column: access hit count
                last_access_at REAL DEFAULT 0  # column: last access timestamp
            )  # table definition end
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_type ON cache_entries(cache_type)  # index on cache_type for filtering
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires_at ON cache_entries(expires_at)  # index on expires_at for cleanup
        """)
        conn.commit()  # SQL string end for table creation
  # SQL string end for idx_cache_type
    def get(self, cache_key: str, cache_type: str = "review_result") -> Optional[Any]:
        """获取缓存值，未命中或过期返回 None"""
        try:  # try block for cache retrieval
            conn = self._get_conn()  # get thread-local connection
            now = time.time()  # current timestamp for expiry check
  # commit schema creation
            # 先清理过期条目（概率性清理，降低写入频率）
            if hash(cache_key) % 100 < 5:  # 5% 概率
                self._cleanup_expired()  # probabilistic expired cleanup

            row = conn.execute(  # execute SELECT query
                "SELECT value, expires_at FROM cache_entries WHERE cache_key = ? AND cache_type = ?",  # SQL: select value and expires_at
                (cache_key, cache_type)  # params: cache_key and cache_type
            ).fetchone()  # fetch first matching row

            if row is None:  # no row found = cache miss
                return None  # return None for miss

            if row["expires_at"] < now:  # check if entry has expired
                # 过期条目，延迟删除
                conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,))  # delete expired entry
                conn.commit()  # commit deletion
                return None  # treat expired as miss

            # 更新访问计数
            conn.execute(  # update access count and last_access
                "UPDATE cache_entries SET access_count = access_count + 1, last_access_at = ? WHERE cache_key = ?",  # SQL: increment access count
                (now, cache_key)  # params: now and cache_key
            )  # execute end
            conn.commit()  # commit metadata update

            return json.loads(row["value"])  # deserialize and return cached value
        except Exception as e:  # catch any database error
            logger.warning(f"缓存读取失败: {e}")  # log warning for read failure
            return None  # return None on error

    def set(self, cache_key: str, value: Any, cache_type: str = "review_result",  # write value to cache
            ttl: Optional[int] = None) -> None:  # optional TTL override
        """写入缓存"""
        try:  # try block for cache write
            if ttl is None:  # check if TTL not provided
                ttl = CACHE_TTL.get(cache_type, 86400)  # use default TTL for this type

            now = time.time()  # current timestamp
            serialized = json.dumps(value, ensure_ascii=False, default=str)  # serialize value to JSON string

            with self._write_lock:  # exclusive lock for write
                conn = self._get_conn()  # get thread-local connection
                conn.execute(  # execute INSERT OR REPLACE
                    """INSERT OR REPLACE INTO cache_entries  # SQL: upsert cache entry
                       (cache_key, cache_type, value, created_at, expires_at, access_count, last_access_at)  # params: key, type, value, timestamps
                       VALUES (?, ?, ?, ?, ?, 0, ?)""",  # execute end
                    (cache_key, cache_type, serialized, now, now + ttl, now)  # SQL string end
                )  # param tuple
  # trim to max entries
                # 限制条目数：删除最旧的条目
                max_entries = MAX_ENTRIES_PER_TYPE.get(cache_type, 500)  # count current entries of type
                count = conn.execute(  # SQL: count by cache_type
                    "SELECT COUNT(*) as cnt FROM cache_entries WHERE cache_type = ?",  # extract count from result
                    (cache_type,)  # SQL string end
                ).fetchone()["cnt"]  # check if exceeds limit
  # SQL: delete exceeding oldest
                if count > max_entries:  # keep newest entries within limit
                    conn.execute(  # SQL subquery: latest by last_access_at
                        """DELETE FROM cache_entries WHERE cache_type = ? AND cache_key NOT IN  # ORDER BY for latest entries
                           (SELECT cache_key FROM cache_entries WHERE cache_type = ?  # LIMIT to max entries
                        # SQL string end for DELETE
                            ORDER BY last_access_at DESC LIMIT ?)""",
                        (cache_type, cache_type, max_entries)  # params: type, type, max_entries
                    )  # execute end

                conn.commit()  # commit all writes
        except Exception as e:  # catch any database error
            logger.warning(f"缓存写入失败: {e}")  # log warning for write failure

    def delete(self, cache_key: str) -> None:  # delete specified cache entry
        """删除指定缓存"""
        try:  # try block for deletion
            conn = self._get_conn()  # get thread-local connection
            conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,))  # delete by cache_key
            conn.commit()  # commit deletion
        except Exception as e:  # catch any database error
            logger.warning(f"缓存删除失败: {e}")  # log warning for delete failure

    def delete_by_type(self, cache_type: str) -> int:  # delete all entries of a type
        """删除指定类型的所有缓存，返回删除条数"""
        try:  # try block for bulk deletion
            conn = self._get_conn()  # get thread-local connection
            cursor = conn.execute("DELETE FROM cache_entries WHERE cache_type = ?", (cache_type,))  # delete by cache_type
            conn.commit()  # commit deletion
            return cursor.rowcount  # return number of deleted rows
        except Exception as e:  # catch any database error
            logger.warning(f"缓存清理失败: {e}")  # log warning for cleanup failure
            return 0  # return 0 on error

    def clear(self) -> None:  # clear all cache entries
        """清空所有缓存"""
        try:  # try block for full cleanup
            conn = self._get_conn()  # get thread-local connection
            conn.execute("DELETE FROM cache_entries")  # delete all entries
            conn.commit()  # commit cleanup
        except Exception as e:  # catch any database error
            logger.warning(f"缓存清空失败: {e}")  # log warning for clear failure

    def stats(self) -> Dict[str, Any]:  # get cache statistics
        """缓存统计"""
        try:  # try block for stats query
            conn = self._get_conn()  # get thread-local connection
            total = conn.execute("SELECT COUNT(*) as cnt FROM cache_entries").fetchone()["cnt"]  # count total entries
            expired = conn.execute(  # count expired entries
                "SELECT COUNT(*) as cnt FROM cache_entries WHERE expires_at < ?",  # SQL: expired entries query
                (time.time(),)  # param: current timestamp
            ).fetchone()["cnt"]  # SQL string end
            by_type = conn.execute(  # count by cache type
                "SELECT cache_type, COUNT(*) as cnt FROM cache_entries GROUP BY cache_type"  # SQL: grouped by cache_type
            ).fetchall()  # fetch all type groups
            return {  # build stats dict
                "total": total,  # field: total entries
                "expired": expired,  # field: expired entries
                "active": total - expired,  # field: active entries
                "by_type": {row["cache_type"]: row["cnt"] for row in by_type},  # field: per-type entry counts
            }  # dict end
        except Exception as e:  # catch any database error
            return {"error": str(e)}  # return error message dict

    def _cleanup_expired(self) -> int:  # cleanup expired entries
        """清理过期条目，返回清理条数"""
        try:  # try block for cleanup
            conn = self._get_conn()  # get thread-local connection
            cursor = conn.execute("DELETE FROM cache_entries WHERE expires_at < ?", (time.time(),))  # delete expired entries
            conn.commit()  # commit cleanup
            return cursor.rowcount  # return cleaned count
        except Exception:  # catch any database error
            return 0  # return 0 on error

    def get_or_compute(self, cache_key: str, compute_fn: Callable,  # cache-aside with auto-fill
                       cache_type: str = "review_result", ttl: Optional[int] = None) -> Any:  # optional TTL override
        """缓存穿透保护：先查缓存，未命中则计算并缓存"""
        cached = self.get(cache_key, cache_type)  # try cache first
        if cached is not None:  # check if cache hit
            return cached  # return cached value

        result = compute_fn()  # compute value on miss
        if result is not None:  # check computed result not None
            self.set(cache_key, result, cache_type, ttl)  # cache computed result
        return result  # return computed value

    def close(self):  # close thread-local connection
        """关闭当前线程的数据库连接"""
        if hasattr(self._local, "conn") and self._local.conn is not None:  # check connection exists and is open
            self._local.conn.close()  # close the connection
            self._local.conn = None  # set connection to None


# ── 便捷函数 ──────────────────────────────────────────────

def make_cache_key(file_hash: str, standard: str = "GB50016", building_type: str = "civil") -> str:  # generate review result cache key
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
    """获取全局缓存实例"""
    global _cache  # modify module-level global
    if _cache is None:  # check singleton not created
        _cache = PersistentCache()  # create new PersistentCache instance
    return _cache  # return global cache instance
