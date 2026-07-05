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
import json
import sqlite3
import threading
import time
import hashlib
import os
import logging
from pathlib import Path
from typing import Any, Optional, Dict, Callable

logger = logging.getLogger(__name__)

# ── 默认缓存路径 ──────────────────────────────────────────
DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")
DEFAULT_DB_PATH = os.path.join(DEFAULT_CACHE_DIR, "baa_cache.db")

# ── 默认 TTL（秒） ───────────────────────────────────────
CACHE_TTL = {
    "drawing_parse": 86400 * 7,    # 7 天
    "review_result": 86400 * 3,     # 3 天
    "semantic_analysis": 86400 * 7, # 7 天
}

# ── 最大条目数限制（防止 SQLite 膨胀） ────────────────────
MAX_ENTRIES_PER_TYPE = {
    "drawing_parse": 500,
    "review_result": 500,
    "semantic_analysis": 500,
}


class PersistentCache:
    """基于 SQLite 的持久化缓存，线程安全"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = DEFAULT_DB_PATH):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        if self._initialized:
            return
        self._initialized = True
        self._db_path = db_path
        self._local = threading.local()
        self._write_lock = threading.Lock()

        # 确保目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # 初始化表
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接（惰性创建）"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-8000")  # 8MB
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        """创建表结构"""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                cache_key TEXT PRIMARY KEY,
                cache_type TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                access_count INTEGER DEFAULT 0,
                last_access_at REAL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_type ON cache_entries(cache_type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires_at ON cache_entries(expires_at)
        """)
        conn.commit()

    def get(self, cache_key: str, cache_type: str = "review_result") -> Optional[Any]:
        """获取缓存值，未命中或过期返回 None"""
        try:
            conn = self._get_conn()
            now = time.time()

            # 先清理过期条目（概率性清理，降低写入频率）
            if hash(cache_key) % 100 < 5:  # 5% 概率
                self._cleanup_expired()

            row = conn.execute(
                "SELECT value, expires_at FROM cache_entries WHERE cache_key = ? AND cache_type = ?",
                (cache_key, cache_type)
            ).fetchone()

            if row is None:
                return None

            if row["expires_at"] < now:
                # 过期条目，延迟删除
                conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,))
                conn.commit()
                return None

            # 更新访问计数
            conn.execute(
                "UPDATE cache_entries SET access_count = access_count + 1, last_access_at = ? WHERE cache_key = ?",
                (now, cache_key)
            )
            conn.commit()

            return json.loads(row["value"])
        except Exception as e:
            logger.warning(f"缓存读取失败: {e}")
            return None

    def set(self, cache_key: str, value: Any, cache_type: str = "review_result",
            ttl: Optional[int] = None) -> None:
        """写入缓存"""
        try:
            if ttl is None:
                ttl = CACHE_TTL.get(cache_type, 86400)

            now = time.time()
            serialized = json.dumps(value, ensure_ascii=False, default=str)

            with self._write_lock:
                conn = self._get_conn()
                conn.execute(
                    """INSERT OR REPLACE INTO cache_entries
                       (cache_key, cache_type, value, created_at, expires_at, access_count, last_access_at)
                       VALUES (?, ?, ?, ?, ?, 0, ?)""",
                    (cache_key, cache_type, serialized, now, now + ttl, now)
                )

                # 限制条目数：删除最旧的条目
                max_entries = MAX_ENTRIES_PER_TYPE.get(cache_type, 500)
                count = conn.execute(
                    "SELECT COUNT(*) as cnt FROM cache_entries WHERE cache_type = ?",
                    (cache_type,)
                ).fetchone()["cnt"]

                if count > max_entries:
                    conn.execute(
                        """DELETE FROM cache_entries WHERE cache_type = ? AND cache_key NOT IN
                           (SELECT cache_key FROM cache_entries WHERE cache_type = ?
                            ORDER BY last_access_at DESC LIMIT ?)""",
                        (cache_type, cache_type, max_entries)
                    )

                conn.commit()
        except Exception as e:
            logger.warning(f"缓存写入失败: {e}")

    def delete(self, cache_key: str) -> None:
        """删除指定缓存"""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,))
            conn.commit()
        except Exception as e:
            logger.warning(f"缓存删除失败: {e}")

    def delete_by_type(self, cache_type: str) -> int:
        """删除指定类型的所有缓存，返回删除条数"""
        try:
            conn = self._get_conn()
            cursor = conn.execute("DELETE FROM cache_entries WHERE cache_type = ?", (cache_type,))
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.warning(f"缓存清理失败: {e}")
            return 0

    def clear(self) -> None:
        """清空所有缓存"""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM cache_entries")
            conn.commit()
        except Exception as e:
            logger.warning(f"缓存清空失败: {e}")

    def stats(self) -> Dict[str, Any]:
        """缓存统计"""
        try:
            conn = self._get_conn()
            total = conn.execute("SELECT COUNT(*) as cnt FROM cache_entries").fetchone()["cnt"]
            expired = conn.execute(
                "SELECT COUNT(*) as cnt FROM cache_entries WHERE expires_at < ?",
                (time.time(),)
            ).fetchone()["cnt"]
            by_type = conn.execute(
                "SELECT cache_type, COUNT(*) as cnt FROM cache_entries GROUP BY cache_type"
            ).fetchall()
            return {
                "total": total,
                "expired": expired,
                "active": total - expired,
                "by_type": {row["cache_type"]: row["cnt"] for row in by_type},
            }
        except Exception as e:
            return {"error": str(e)}

    def _cleanup_expired(self) -> int:
        """清理过期条目，返回清理条数"""
        try:
            conn = self._get_conn()
            cursor = conn.execute("DELETE FROM cache_entries WHERE expires_at < ?", (time.time(),))
            conn.commit()
            return cursor.rowcount
        except Exception:
            return 0

    def get_or_compute(self, cache_key: str, compute_fn: Callable,
                       cache_type: str = "review_result", ttl: Optional[int] = None) -> Any:
        """缓存穿透保护：先查缓存，未命中则计算并缓存"""
        cached = self.get(cache_key, cache_type)
        if cached is not None:
            return cached

        result = compute_fn()
        if result is not None:
            self.set(cache_key, result, cache_type, ttl)
        return result

    def close(self):
        """关闭当前线程的数据库连接"""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None


# ── 便捷函数 ──────────────────────────────────────────────

def make_cache_key(file_hash: str, standard: str = "GB50016", building_type: str = "civil") -> str:
    """生成审查结果缓存键"""
    return f"{file_hash}:{standard}:{building_type}"


def make_drawing_cache_key(file_hash: str) -> str:
    """生成图纸解析缓存键"""
    return f"drawing:{file_hash}"


def make_semantic_cache_key(primitives_hash: str) -> str:
    """生成语义分析缓存键"""
    return f"semantic:{primitives_hash}"


# ── 全局单例 ──────────────────────────────────────────────
_cache: Optional[PersistentCache] = None


def get_cache() -> PersistentCache:
    """获取全局缓存实例"""
    global _cache
    if _cache is None:
        _cache = PersistentCache()
    return _cache