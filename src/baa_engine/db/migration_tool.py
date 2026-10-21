"""
T-C1 存量数据搬迁工具：旧三 SQLite 库 → 统一数据层目标库。

数据源（只读 URI 连接，永不修改/删除，回滚路径 = 新库异常时回指旧文件）：
- {PROJECT_ROOT}/data/review_history.db   → review_history + review_audit_items
- {PROJECT_ROOT}/src/data/cache/baa_cache.db → cache_entries
- {PROJECT_ROOT}/src/data/collab/baa_collab.db → 协作域 10 表

目标：resolve_database_url()（--url 覆盖），PG / SQLite 均可。

幂等：按主键 INSERT OR IGNORE（SQLite）/ ON CONFLICT DO NOTHING（PG），
可重复执行且不覆盖目标库中更新的数据；输出各表行数比对报告。

类型转换（仅历史/审计域）：
- review_history.created_at/updated_at：ISO TEXT → DateTime(timezone=True)
- review_audit_items.created_at（CURRENT_TIMESTAMP）/reviewed_at：TEXT → DateTime
- JSON 文本列（summary/details/corrections/tags/file_ids/result_summary）：
  json.loads 后写 JSON 列，双编码值兜底原样存字符串
其余（缓存域/协作域时间戳）为 Float epoch，零转换直拷。

用法：
    python -m src.baa_engine.db.migration_tool --dry-run
    python -m src.baa_engine.db.migration_tool [--url sqlite:///D:/.../baa.db]
"""

import argparse
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import insert, select
from sqlalchemy.orm import Session  # noqa: F401

from src.baa_engine.db import ensure_schema, get_session_factory, resolve_database_url
from src.baa_engine.db.models import audit, cache, collab, history  # noqa: F401
from src.baa_engine.db.models.audit import ReviewAuditItem
from src.baa_engine.db.models.cache import CacheEntry
from src.baa_engine.db.models.collab import (
    ApprovalFlow,
    ApprovalStep,
    Project,
    ProjectMember,
    ReviewComment,
    ReviewSession,
    RectificationRecord,
    Team,
    TeamMember,
    User,
)
from src.baa_engine.db.models.history import ReviewHistory

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# legacy 源库位置（与各模块历史路径解析一致）
SOURCE_HISTORY_DB = PROJECT_ROOT / "data" / "review_history.db"
SOURCE_CACHE_DB = PROJECT_ROOT / "src" / "data" / "cache" / "baa_cache.db"
SOURCE_COLLAB_DB = PROJECT_ROOT / "src" / "data" / "collab" / "baa_collab.db"


def _connect_ro(path: Path) -> sqlite3.Connection:
    """只读连接 legacy SQLite（不存在则抛 FileNotFoundError，由调用方跳过）。"""
    uri = f"file:{path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _parse_json(value: Any) -> Any:
    """JSON 文本列转换：解析失败（如双编码之外的非 JSON 串）原样返回。"""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _parse_dt(value: Any, assume_utc: bool = True) -> Optional[datetime]:
    """时间戳转换：ISO / CURRENT_TIMESTAMP 文本 → datetime。"""
    if value is None or isinstance(value, datetime):
        return value
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        logger.warning("时间戳解析失败，置 NULL: %r", value)
        return None
    if assume_utc and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _cols(model) -> List[str]:
    return [c.name for c in model.__table__.columns]


# 搬迁计划：(源库路径, 表名, 模型, 字段变换)
MIGRATION_PLAN: List[Dict[str, Any]] = [
    {
        "source": SOURCE_HISTORY_DB,
        "table": "review_history",
        "model": ReviewHistory,
        "transform": lambda r: {
            **r,
            "summary": _parse_json(r.get("summary")),
            "details": _parse_json(r.get("details")),
            "corrections": _parse_json(r.get("corrections")),
            "created_at": _parse_dt(r.get("created_at")),
            "updated_at": _parse_dt(r.get("updated_at")),
        },
    },
    {
        "source": SOURCE_HISTORY_DB,
        "table": "review_audit_items",
        "model": ReviewAuditItem,
        "transform": lambda r: {
            **r,
            "created_at": _parse_dt(r.get("created_at"), assume_utc=False),
            "reviewed_at": _parse_dt(r.get("reviewed_at"), assume_utc=False),
        },
        # FK 守卫：旧 SQLite 库不强制外键，存在 review_id 指向不存在 history 的孤儿行；
        # 新统一 schema 有 FK 约束，孤儿行跳过并计入 skipped（新库完整性优先）
        "guard": lambda data, session: (
            data.get("review_id") is not None
            and session.get(ReviewHistory, data["review_id"]) is not None
        ),
    },
    {
        "source": SOURCE_CACHE_DB,
        "table": "cache_entries",
        "model": CacheEntry,
        "transform": lambda r: dict(r),  # value 保持 TEXT JSON 串，Float epoch 直拷
    },
    {
        "source": SOURCE_COLLAB_DB,
        "table": "users",
        "model": User,
        "transform": dict,
    },
    {
        "source": SOURCE_COLLAB_DB,
        "table": "teams",
        "model": Team,
        "transform": dict,
    },
    {
        "source": SOURCE_COLLAB_DB,
        "table": "team_members",
        "model": TeamMember,
        "transform": dict,
    },
    {
        "source": SOURCE_COLLAB_DB,
        "table": "projects",
        "model": Project,
        "transform": lambda r: {**r, "tags": _parse_json(r.get("tags"))},
    },
    {
        "source": SOURCE_COLLAB_DB,
        "table": "project_members",
        "model": ProjectMember,
        "transform": dict,
    },
    {
        "source": SOURCE_COLLAB_DB,
        "table": "review_sessions",
        "model": ReviewSession,
        "transform": lambda r: {
            **r,
            "file_ids": _parse_json(r.get("file_ids")),
            "result_summary": _parse_json(r.get("result_summary")),
        },
    },
    {
        "source": SOURCE_COLLAB_DB,
        "table": "rectification_records",
        "model": RectificationRecord,
        "transform": dict,
    },
    {
        "source": SOURCE_COLLAB_DB,
        "table": "review_comments",
        "model": ReviewComment,
        "transform": dict,
    },
    {
        "source": SOURCE_COLLAB_DB,
        "table": "approval_flows",
        "model": ApprovalFlow,
        "transform": dict,
    },
    {
        "source": SOURCE_COLLAB_DB,
        "table": "approval_steps",
        "model": ApprovalStep,
        "transform": dict,
    },
]


def _insert_stmt(model, target_url: str):
    """按方言构造幂等插入：SQLite → INSERT OR IGNORE；PG → ON CONFLICT DO NOTHING。"""
    if target_url.strip().lower().startswith("sqlite"):
        return insert(model).prefix_with("OR IGNORE")
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    pk_cols = [c.name for c in model.__table__.primary_key.columns]
    return pg_insert(model).on_conflict_do_nothing(index_elements=pk_cols)


def migrate(
    dry_run: bool = False,
    target_url: Optional[str] = None,
    sources: Optional[Dict[str, Path]] = None,
) -> Dict[str, Dict[str, int]]:
    """执行搬迁，返回 {table: {source, inserted, target_total}} 报告。

    Args:
        dry_run: 仅统计，不写入
        target_url: 目标库 URL（默认 resolve_database_url()）
        sources: 覆盖源库路径 {"history": ..., "cache": ..., "collab": ...}（测试用）
    """
    url = resolve_database_url(target_url)
    sources = sources or {}
    src_map = {
        "history": sources.get("history", SOURCE_HISTORY_DB),
        "cache": sources.get("cache", SOURCE_CACHE_DB),
        "collab": sources.get("collab", SOURCE_COLLAB_DB),
    }
    sf = get_session_factory(url)
    ensure_schema(url)  # 目标 schema 兜底（生产由 Alembic 预先建表，此处幂等）
    session = sf()
    report: Dict[str, Dict[str, int]] = {}
    try:
        for entry in MIGRATION_PLAN:
            table = entry["table"]
            model = entry["model"]
            source = src_map[entry.get("source_key", _source_key(entry["source"]))]
            report[table] = {"source": 0, "inserted": 0, "target_total": 0}
            if not Path(source).exists():
                report[table]["error"] = 1  # 源缺失标记
                continue
            con = _connect_ro(Path(source))
            try:
                has_table = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                if not has_table:
                    # 旧库版本落后（如 rectification_records 为 T-B6 后加）：缺表视为无数据
                    report[table]["error"] = 1
                    logger.warning("源库缺表 %s（跳过）: %s", table, source)
                    continue
                rows = con.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
            finally:
                con.close()
            report[table]["source"] = len(rows)
            if dry_run:
                report[table]["target_total"] = session.scalar(func_count(model)) or 0
                continue
            model_cols = set(_cols(model))
            stmt = _insert_stmt(model, url)
            guard = entry.get("guard")
            skipped = 0
            before = session.scalar(func_count(model)) or 0
            for row in rows:
                raw = {k: row[k] for k in row.keys() if k in model_cols}
                data = entry["transform"](raw)
                if guard is not None and not guard(data, session):
                    skipped += 1  # 孤儿行（FK 引用缺失），保持新库完整性
                    continue
                # Core 路径执行（session.execute 会走 ORM bulk 返回 IteratorResult，无 rowcount）
                session.connection().execute(stmt, data)
            session.commit()
            after = session.scalar(func_count(model)) or 0
            report[table]["inserted"] = after - before  # 表级净增（驱动无关；幂等重跑=0）
            report[table]["skipped"] = skipped
            report[table]["target_total"] = after
        return report
    finally:
        sf.remove()


def _source_key(source_path: Path) -> str:
    """把 MIGRATION_PLAN 里的默认源路径映射到 src_map 键。"""
    p = Path(source_path)
    if p == SOURCE_CACHE_DB:
        return "cache"
    if p == SOURCE_COLLAB_DB:
        return "collab"
    return "history"


def func_count(model):
    """行数 select（session.scalar 直接消费）。"""
    from sqlalchemy import func

    return select(func.count()).select_from(model)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="T-C1 存量数据搬迁：旧三库 → 统一数据层")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不写入")
    parser.add_argument("--url", default=None, help="目标库 URL（默认 BAA_DATABASE_URL / 回退 SQLite）")
    args = parser.parse_args(argv)

    report = migrate(dry_run=args.dry_run, target_url=args.url)
    print(f"{'table':<24}{'source':>8}{'inserted':>10}{'target_total':>14}")
    total_src = total_dst = 0
    for table, r in report.items():
        err = ""
        if r.get("error"):
            err = " (源缺失/缺表)"
        if r.get("skipped"):
            err += f" (跳过孤儿{r['skipped']}条)"
        print(f"{table:<24}{r['source']:>8}{r['inserted']:>10}{r['target_total']:>14}{err}")
        total_src += r["source"]
        total_dst += r["target_total"]
    print(f"\n合计 source={total_src} target_total={total_dst} dry_run={args.dry_run}")
    print("旧三文件原样保留（回滚路径：停写 + 回指旧库）。")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
