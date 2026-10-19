"""
T-B1: 拓扑显式化 API

端点: POST /api/v1/topology
输入: analyze 结果的 entities 数组（自包含，无存储耦合）
返回: 可 JSON 化拓扑结构（节点/边/邻接/连通分量），供判定层消费
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from src.api.api_globals import verify_api_key
from src.baa_engine.semantic_analyzer.models import SemanticEntity
from src.baa_engine.semantic_analyzer.topology import (
    build_topology_graph,
    topology_summary,
)

router = APIRouter(tags=["topology"])


def _to_entity(raw: Dict[str, Any]) -> Optional[SemanticEntity]:
    """entities JSON 条目 → SemanticEntity（缺 id/type/bbox 丢弃）。"""
    eid = raw.get("id")
    etype = raw.get("type")
    bbox = raw.get("bbox")
    if not eid or not etype or not isinstance(bbox, dict):
        return None
    return SemanticEntity(
        entity_id=str(eid),
        entity_type=str(etype),
        bbox=bbox,
        layer=str(raw.get("layer", "") or ""),
        properties=raw.get("properties") or {},
    )


@router.post("/api/v1/topology")
async def build_topology(
    payload: Dict[str, Any],
    api_key: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """从 entities 构建空间拓扑（房间邻接/门窗连接/连通分量）。

    请求体: {"entities": [{"id","type","bbox","layer","properties"}, ...]}
    """
    raw_entities = payload.get("entities")
    if not isinstance(raw_entities, list):
        return {"status": "error", "error": "entities must be a list"}
    entities = [e for e in (_to_entity(r) for r in raw_entities) if e is not None]
    g = build_topology_graph(entities)
    summary = topology_summary(g)
    return {
        "status": "ok",
        "input_count": len(raw_entities),
        "consumed_count": len(entities),
        **summary,
    }
