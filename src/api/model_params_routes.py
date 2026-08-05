"""
P93: 模型参数导出 API 路由

前缀: /api/v1/model-params
端点:
  GET  /api/v1/model-params/functions        — 原子函数参数表
  GET  /api/v1/model-params/layer-rules       — LAYER_RULES 语义映射
  GET  /api/v1/model-params/cd-items          — 施工图审查标准 (CD)
  GET  /api/v1/model-params/samples           — 审查样本 (SFT 三元组)
  GET  /api/v1/model-params/spatial-graph     — 空间关系图
  GET  /api/v1/model-params/export            — 统一格式导出
"""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, JSONResponse

from src.baa_engine.atomic_functions import FuncRegistry
from src.baa_engine.model_params import exporter as mp_exporter

router = APIRouter(tags=["model-params", "模型参数"])

_REGISTRY: Optional[FuncRegistry] = None


def _get_registry() -> FuncRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = FuncRegistry()
    return _REGISTRY


# ── 1. 原子函数参数表 ──────────────────────────────────

@router.get("/model-params/functions")  # noqa: F811
def get_functions(
    limit: Optional[int] = Query(None, ge=1, le=5000, description="返回条数上限"),
    category: Optional[str] = Query(None, description="按分类过滤 (dimension/dist/exist/area/...)"),
) -> Dict[str, Any]:
    """返回 422 个原子函数的完整参数结构"""
    funcs = mp_exporter.get_function_params(_get_registry())
    if category:
        funcs = [f for f in funcs if f["category"] == category]
    if limit:
        funcs = funcs[:limit]
    return {
        "status": "success",
        "total": len(funcs),
        "data": funcs,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ── 2. LAYER_RULES 语义映射 ────────────────────────────

@router.get("/model-params/layer-rules")  # noqa: F811
def get_layer_rules(
    limit: Optional[int] = Query(None, ge=1, le=2000),
    source: Optional[str] = Query(None, description="LAYER_RULES / SHORT_LAYER_RULES"),
) -> Dict[str, Any]:
    """返回 657 条图层→实体类型语义映射"""
    rules = mp_exporter.get_layer_rules()
    if source:
        rules = [r for r in rules if r["source"] == source]
    if limit:
        rules = rules[:limit]
    return {
        "status": "success",
        "total": len(rules),
        "data": rules,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ── 3. CD 审查项 ─────────────────────────────────────

@router.get("/model-params/cd-items")  # noqa: F811
def get_cd_items(
    level: Optional[str] = Query(None, description="L1 / L2 / L3"),
    major: Optional[str] = Query(None, description="arch/struct/mech/elec/plumb"),
) -> Dict[str, Any]:
    """返回 30 条施工图审查标准项"""
    items = mp_exporter.get_construction_review_params()
    if level:
        items = [i for i in items if i["level"] == level]
    if major:
        items = [i for i in items if i["major"] == major]
    return {
        "status": "success",
        "total": len(items),
        "data": items,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ── 4. 审查样本 (SFT 三元组) ─────────────────────────

@router.get("/model-params/samples")  # noqa: F811
def get_review_samples(
    limit: int = Query(50, ge=1, le=500, description="返回样本数"),
    review_id: Optional[str] = Query(None, description="按 review_id 过滤"),
) -> Dict[str, Any]:
    """从已完成审查中提取 SFT 样本三元组"""
    samples = mp_exporter.get_review_samples(limit=limit, review_id=review_id)
    return {
        "status": "success",
        "total": len(samples),
        "data": samples,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ── 5. 空间关系图 ────────────────────────────────────

@router.get("/model-params/spatial-graph")  # noqa: F811
def get_spatial_graph(
    review_id: str = Query(..., description="审查任务ID"),
) -> Dict[str, Any]:
    """提取空间关系（节点+边+几何属性）"""
    graph = mp_exporter.get_spatial_graph(review_id)
    if "error" in graph:
        raise HTTPException(status_code=404, detail=graph["error"])
    return {
        "status": "success",
        "data": graph,
    }


# ── 6. 统一导出 ─────────────────────────────────────

@router.get("/model-params/export")  # noqa: F811
def export_model_params(
    format: str = Query("json", regex="json|jsonl-sft|hf-dataset|csv",
                        description="json|jsonl-sft|hf-dataset|csv"),
    limit: int = Query(500, ge=1, le=5000, description="样本上限"),
) -> Any:
    """
    统一导出端点，支持多种格式：
    - json: 原始结构化 JSON
    - jsonl-sft: OpenAI/Qwen/DeepSeek 通用 SFT 格式
    - hf-dataset: HuggingFace Dataset 描述
    - csv: 表格格式
    """
    funcs = mp_exporter.get_function_params(_get_registry())
    rules = mp_exporter.get_layer_rules()
    cd_items = mp_exporter.get_construction_review_params()

    if limit:
        funcs = funcs[:limit]
        rules = rules[:limit]
        cd_items = cd_items[:limit]

    if format == "jsonl-sft":
        content = mp_exporter.to_sft_jsonl(funcs, rules, cd_items)
        return Response(
            content=content,
            media_type="text/plain",
            headers={
                "Content-Disposition": "attachment; filename=baa-sft-data.jsonl",
            },
        )

    elif format == "hf-dataset":
        data = mp_exporter.to_hf_dataset_description(funcs, rules, cd_items)
        return JSONResponse(content=data)

    elif format == "csv":
        lines = [
            "#,type,source,id,title,operator,threshold,unit,standard_ref",
        ]
        idx = 0
        for f in funcs:
            idx += 1
            lines.append(
                f"{idx},function,atomic,{f['func_id']},{f['title']},"
                f"{f['operator']},{f['threshold']},{f['unit']},{f['clause_id']}"
            )
        for r in rules:
            idx += 1
            lines.append(
                f"{idx},layer_rule,semantic,{r['pattern']},{r['entity_type']},,,,,{r['source']}"
            )
        for i in cd_items:
            idx += 1
            lines.append(
                f"{idx},cd_item,construction_review,{i['item_id']},{i['title']},"
                f",{i['weight']},,,{i['standard_ref']}"
            )
        content = "\n".join(lines)
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=baa-model-params.csv",
            },
        )

    else:  # json
        return {
            "status": "success",
            "format": format,
            "generated_at": datetime.utcnow().isoformat(),
            "statistics": {
                "functions": len(funcs),
                "layer_rules": len(rules),
                "cd_items": len(cd_items),
            },
            "data": {
                "functions": funcs,
                "layer_rules": rules,
                "cd_items": cd_items,
            },
        }
