"""
P72: 审查统计仪表盘 API

端点: /api/v1/stats
返回: 审查总览、趋势、违规分布、置信度分布、实体类型分布、API 调用量
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, Query

from .api_globals import verify_api_key
from src.api.review.review_history import list_review_history


def _parse_details(details_json: str) -> list:
    """安全解析 details JSON 字符串"""
    import json

    if not details_json:
        return []
    try:
        return json.loads(details_json)
    except Exception:
        return []


async def get_stats(
    days: int = Query(30, description="统计最近 N 天的趋势数据", ge=1, le=365),
    api_key: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """获取审查统计仪表盘数据

    返回结构:
    {
        "overview": {
            "total_reviews": int,
            "total_drawings": int,
            "total_violations": int,
            "avg_compliance_rate": float,
            "avg_processing_time_ms": float,
        },
        "trend": [
            {"date": "2026-07-25", "reviews": int, "violations": int}
        ],
        "violation_distribution": {
            "critical": int,
            "major": int,
            "minor": int,
            "pass": int,
        },
        "confidence_distribution": {
            "confirmed": int,
            "suspected": int,
            "needs_review": int,
        },
        "entity_type_distribution": {"wall": int, "door": int, ...},
        "building_type_distribution": {"civil": int, "industrial": int},
        "api_key_usage": {
            "total_calls": int,
            "keys": {key_id: {"total_calls": int, ...}}
        },
        "top_violations": [
            {"clause_id": str, "title": str, "count": int}
        ]
    }
    """
    from src.api.api_globals import get_key_manager

    # 获取所有审查记录
    result = list_review_history(limit=10000, status="success")
    items = result.get("items", [])

    # 过滤最近 N 天
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent_items = []
    for item in items:
        reviewed_at = item.get("reviewedAt") or item.get("createdAt")
        if reviewed_at:
            try:
                dt = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
                if dt >= cutoff:
                    recent_items.append(item)
            except Exception:
                pass

    # ── 总览 ──
    total_reviews = len(recent_items)
    total_violations = sum(r.get("violationCount", 0) for r in recent_items)
    scores = [r.get("score", 0) for r in recent_items if r.get("score") is not None]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    times = [
        r.get("processingTimeMs", 0) for r in recent_items if r.get("processingTimeMs") is not None
    ]
    avg_time = sum(times) / len(times) if times else 0.0

    # ── 趋势（按天聚合） ──
    trend: Dict[str, Dict[str, int]] = {}
    for r in recent_items:
        reviewed_at = r.get("reviewedAt") or r.get("createdAt")
        if reviewed_at:
            try:
                dt = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
                date_key = dt.strftime("%Y-%m-%d")
                if date_key not in trend:
                    trend[date_key] = {"date": date_key, "reviews": 0, "violations": 0}
                trend[date_key]["reviews"] += 1
                trend[date_key]["violations"] += r.get("violationCount", 0)
            except Exception:
                pass
    trend_list = sorted(trend.values(), key=lambda x: x["date"])

    # ── 违规分布 + 置信度 + 实体类型 + 建筑类型（需读取 detail） ──
    violation_dist = {"critical": 0, "major": 0, "minor": 0, "pass": 0}
    confidence_dist = {"confirmed": 0, "suspected": 0, "needs_review": 0}
    entity_dist: Dict[str, int] = {}
    building_dist: Dict[str, int] = {}
    clause_counter: Dict[str, Dict[str, Any]] = {}

    # 用线程池并行解析大量 JSON
    def _parse_one(item):
        from .review.review_history import get_review_detail

        detail = get_review_detail(item["id"])
        if not detail:
            return {}
        details = detail.get("details", [])
        violations = {"critical": 0, "major": 0, "minor": 0, "pass": 0}
        confs = {"confirmed": 0, "suspected": 0, "needs_review": 0}
        entities = {}
        clauses = {}
        for d in details:
            sev = d.get("severity", "minor")
            if sev in violations:
                violations[sev] += 1
            tier = d.get("confidence_tier", "suspected")
            if tier in confs:
                confs[tier] += 1
            etype = d.get("entity_type") or d.get("type")
            if etype:
                entities[etype] = entities.get(etype, 0) + 1
            cid = d.get("clause_id", "")
            if cid:
                if cid not in clauses:
                    clauses[cid] = {
                        "clause_id": cid,
                        "title": d.get("clause_title", ""),
                        "count": 0,
                    }
                clauses[cid]["count"] += 1
        return {
            "violations": violations,
            "confs": confs,
            "entities": entities,
            "clauses": clauses,
        }

    # 线程池并行解析
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=min(4, len(recent_items) or 1)) as pool:
        futures = [pool.submit(_parse_one, item) for item in recent_items]
        for f in futures:
            data = f.result()
            # 违规分布
            for k in violation_dist:
                violation_dist[k] += data.get("violations", {}).get(k, 0)
            # 置信度
            for k in confidence_dist:
                confidence_dist[k] += data.get("confs", {}).get(k, 0)
            # 实体类型
            for k, v in data.get("entities", {}).items():
                entity_dist[k] = entity_dist.get(k, 0) + v
            # 条款计数
            for k, v in data.get("clauses", {}).items():
                if k not in clause_counter:
                    clause_counter[k] = v
                else:
                    clause_counter[k]["count"] += v["count"]

    # 建筑类型分布
    for r in recent_items:
        bt = r.get("buildingType", "civil")
        building_dist[bt] = building_dist.get(bt, 0) + 1

    # TOP 违规条款（按出现次数排序）
    top_violations = sorted(clause_counter.values(), key=lambda x: x["count"], reverse=True)[:10]

    # API key 调用统计
    km = get_key_manager()
    key_stats = km.get_usage_stats()
    total_calls = sum(s.get("total_calls", 0) for s in key_stats.values())

    return {
        "status": "ok",
        "days": days,
        "overview": {
            "total_reviews": total_reviews,
            "total_drawings": total_reviews,  # 每次审查对应一张图纸
            "total_violations": total_violations,
            "avg_compliance_rate": round(avg_score / 100, 4),
            "avg_compliance_score": round(avg_score, 2),
            "avg_processing_time_ms": round(avg_time, 2),
        },
        "trend": trend_list,
        "violation_distribution": violation_dist,
        "confidence_distribution": confidence_dist,
        "entity_type_distribution": dict(
            sorted(entity_dist.items(), key=lambda x: x[1], reverse=True)
        ),
        "building_type_distribution": building_dist,
        "api_key_usage": {
            "total_calls": total_calls,
            "keys": key_stats,
        },
        "top_violations": top_violations,
    }
