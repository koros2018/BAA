"""
P68: 行业案例库 — 审查报告案例展示与检索

核心能力：
1. 从 review_history 中筛选优质案例（高分/高违规/典型场景）
2. 关键词检索（按图纸名称、标准、建筑类型）
3. 案例标签（按违规类型自动归类）
4. 案例详情页（复用 review_detail 数据结构）

API 端点：
- GET /api/v1/cases: 案例列表（分页 + 筛选）
- GET /api/v1/cases/search?q=...: 关键词检索
- GET /api/v1/cases/{case_id}: 单条案例详情
- GET /api/v1/cases/stats: 案例统计（按建筑类型/标准/违规类型分布）
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import Depends
from fastapi.routing import APIRouter

from ..api_key_manager import verify_api_key
from .review_history import list_review_history, get_review_detail

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Cases"])


# ── 案例自动标签（基于违规类型）───────────────────────────────

# 违规 func_id → 案例标签映射
CASE_TAG_MAP = {
    "DIM": "尺寸不合规",
    "DIST": "距离不合规",
    "COUNT": "数量不合规",
    "EXIST": "缺失设施",
    "AREA": "面积不合规",
    "ATTR": "属性不合规",
    "LIGHT": "照明不合规",
    "ACCESS": "无障碍不合规",
}


def _classify_case_tags(details: List[Dict]) -> List[str]:
    """根据审查详情中的 func_id 自动生成案例标签"""
    tags = set()
    for d in details:
        func_id = d.get("func_id", "")
        if not func_id:
            continue
        prefix = func_id.split("-")[0] if "-" in func_id else ""
        tag = CASE_TAG_MAP.get(prefix)
        if tag:
            tags.add(tag)
    return sorted(tags)


def _extract_top_violations(details: List[Dict], limit: int = 5) -> List[Dict]:
    """提取 TOP-N 违规（按 severity × confidence 排序）"""
    scored = []
    for d in details:
        severity = d.get("severity", 0)
        confidence = d.get("confidence", 0.5)
        score = severity * confidence
        scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored[:limit]]


def _format_case_item(row: dict) -> Dict:
    """将 review_history 行格式化案例展示项"""
    details = json.loads(row.get("details", "[]")) if row.get("details") else []
    corrections = json.loads(row.get("corrections", "[]")) if row.get("corrections") else []
    tags = _classify_case_tags(details)
    top_violations = _extract_top_violations(details)

    return {
        "caseId": row.get("id"),
        "drawingName": row.get("drawingName", row.get("drawing_name")),
        "buildingType": row.get("buildingType", row.get("building_type", "civil")),
        "standard": row.get("standard", "GB 50016-2014"),
        "score": row.get("score", 0),
        "violationCount": row.get("violationCount", row.get("violation_count", 0)),
        "entityCount": row.get("entityCount", row.get("entity_count", 0)),
        "correctionCount": row.get("correctionCount", row.get("correction_count", 0)),
        "reviewedAt": row.get("reviewedAt", row.get("created_at")),
        "tags": tags,
        "topViolations": [
            {
                "clause_id": v.get("clause_id", ""),
                "clause_title": v.get("clause_title", ""),
                "entity_type": v.get("entity_type", ""),
                "severity": v.get("severity", 0),
                "confidence_tier": v.get("confidence_tier", ""),
            }
            for v in top_violations
        ],
    }


# ── API 端点 ─────────────────────────────────────────────────

@router.get("/cases", tags=["Cases"])
async def list_cases(
    building_type: Optional[str] = None,
    standard: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    tag: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    api_key: str = Depends(verify_api_key),
):
    """案例列表（分页 + 多维筛选）

    Args:
        building_type: 建筑类型（civil/industrial）
        standard: 审查标准
        min_score / max_score: 得分范围筛选
        tag: 标签筛选（如 "尺寸不合规"）
        limit / offset: 分页
    """
    result = list_review_history(limit=limit, offset=offset, building_type=building_type, status="success")
    items = result.get("items", [])

    # 二次筛选：得分范围
    if min_score is not None or max_score is not None:
        filtered = []
        for item in items:
            score = item.get("score", 0)
            if min_score is not None and score < min_score:
                continue
            if max_score is not None and score > max_score:
                continue
            filtered.append(item)
        items = filtered

    # 二次筛选：标签
    if tag:
        filtered = []
        for item in items:
            detail = get_review_detail(item.get("id", ""))
            if detail:
                details = detail.get("details", [])
                tags = _classify_case_tags(details)
                if tag in tags:
                    filtered.append(item)
        items = filtered

    cases = [_format_case_item(row) for row in items]

    return {
        "status": "ok",
        "total": len(cases),
        "limit": limit,
        "offset": offset,
        "cases": cases,
    }


@router.get("/cases/search", tags=["Cases"])
async def search_cases(
    q: str,
    limit: int = 20,
    api_key: str = Depends(verify_api_key),
):
    """关键词检索案例（按图纸名称模糊匹配）"""
    result = list_review_history(limit=limit * 3, drawing_name=q, status="success")
    items = result.get("items", [])
    cases = [_format_case_item(row) for row in items][:limit]
    return {"status": "ok", "query": q, "total": len(cases), "cases": cases}


@router.get("/cases/{case_id}", tags=["Cases"])
async def get_case(case_id: str, api_key: str = Depends(verify_api_key)):
    """获取单条案例详情（复用 review_detail 数据）"""
    detail = get_review_detail(case_id)
    if not detail:
        return {"status": "error", "message": f"案例 {case_id} 不存在"}
    details = detail.get("details", [])
    tags = _classify_case_tags(details)
    top_violations = _extract_top_violations(details)
    return {
        "status": "ok",
        "caseId": detail["id"],
        "drawingName": detail.get("drawingName", ""),
        "buildingType": detail.get("buildingType", ""),
        "standard": detail.get("standard", ""),
        "score": detail.get("score", 0),
        "violationCount": detail.get("violationCount", 0),
        "entityCount": detail.get("entityCount", 0),
        "correctionCount": len(detail.get("corrections", [])),
        "reviewedAt": detail.get("reviewedAt", ""),
        "tags": tags,
        "topViolations": [
            {
                "clause_id": v.get("clause_id", ""),
                "clause_title": v.get("clause_title", ""),
                "entity_type": v.get("entity_type", ""),
                "extracted_value": v.get("extracted_value"),
                "required_value": v.get("required_value"),
                "difference": v.get("difference"),
                "severity": v.get("severity", 0),
                "confidence_tier": v.get("confidence_tier", ""),
            }
            for v in top_violations
        ],
        "corrections": detail.get("corrections", []),
    }


@router.get("/cases/stats", tags=["Cases"])
async def get_case_stats(api_key: str = Depends(verify_api_key)):
    """案例统计概览（按建筑类型/标准/标签分布）"""
    all_items = list_review_history(limit=9999, status="success").get("items", [])

    by_building_type = {}
    by_standard = {}
    tag_count = {}
    total_score = 0.0
    score_count = 0
    total_violations = 0

    for item in all_items:
        bt = item.get("buildingType", item.get("building_type", "civil"))
        std = item.get("standard", "GB 50016-2014")
        by_building_type[bt] = by_building_type.get(bt, 0) + 1
        by_standard[std] = by_standard.get(std, 0) + 1

        score = item.get("score", 0)
        total_score += score
        score_count += 1
        total_violations += item.get("violationCount", item.get("violation_count", 0))

        # 标签统计
        detail = get_review_detail(item.get("id", ""))
        if detail:
            details = detail.get("details", [])
            for tag in _classify_case_tags(details):
                tag_count[tag] = tag_count.get(tag, 0) + 1

    return {
        "status": "ok",
        "totalCases": len(all_items),
        "totalViolations": total_violations,
        "avgScore": round(total_score / score_count, 1) if score_count else 0,
        "byBuildingType": dict(sorted(by_building_type.items(), key=lambda x: -x[1])),
        "byStandard": dict(sorted(by_standard.items(), key=lambda x: -x[1])),
        "topTags": dict(sorted(tag_count.items(), key=lambda x: -x[1])[:10]),
    }
