"""
P93: 模型参数导出器

导出 BAA 审查引擎的判定规则、阈值、审查样本、空间关系，
供下游开源大模型（Qwen / DeepSeek / 等）做 SFT / RLHF 微调。
"""

import json
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

from typing import Any, Dict, List, Optional

from ..atomic_functions import AtomicFunction, FuncRegistry
from ..spec_data.construction_review import (
    CONSTRUCTION_REVIEW_ITEMS,
    ConstructionReviewItem,
)
from ..semantic_analyzer import LAYER_RULES, SHORT_LAYER_RULES

# ── 1. 原子函数参数表 ─────────────────────────────────────


def get_function_params(registry: Optional[FuncRegistry] = None) -> List[Dict[str, Any]]:
    """
    返回所有原子函数的完整参数结构。
    每条：func_id, title, category, clause_id, description,
          operator, threshold, unit, target_entities,
          depends_on, requires_global_context, check_method
    """
    if registry is None:
        registry = FuncRegistry()
    result = []
    for fid, func in sorted(registry._funcs.items()):
        result.append(
            {
                "func_id": func.func_id,
                "title": func.name,
                "category": func.category.value,
                "clause_id": func.clause_id,
                "description": func.description,
                "operator": func.operator,
                "threshold": func.threshold,
                "unit": func.unit,
                "target_entities": func.target_entities,
                "depends_on": func.depends_on,
                "requires_global_context": func.requires_global_context,
                "check_method": "auto" if func.operator else "manual",
            }
        )
    return result


# ── 2. LAYER_RULES 语义映射 ───────────────────────────────


def get_layer_rules() -> List[Dict[str, Any]]:
    """
    返回 LAYER_RULES + SHORT_LAYER_RULES 的所有语义映射。
    每条：pattern, entity_type, source, priority
    source: "LAYER_RULES" 或 "SHORT_LAYER_RULES"
    priority: 0=LAYER_RULES(长关键字优先), 1=SHORT_LAYER_RULES(全词匹配)
    """
    result = []
    # LAYER_RULES 长关键字（子串匹配，优先级高）
    for pattern, entity_type in sorted(LAYER_RULES.items()):
        result.append(
            {
                "pattern": pattern,
                "entity_type": entity_type,
                "source": "LAYER_RULES",
                "priority": 0,
                "match_type": "substring",
            }
        )
    # SHORT_LAYER_RULES 短关键字（全词匹配，优先级低）
    for pattern, entity_type in sorted(SHORT_LAYER_RULES.items()):
        result.append(
            {
                "pattern": pattern,
                "entity_type": entity_type,
                "source": "SHORT_LAYER_RULES",
                "priority": 1,
                "match_type": "full_word",
            }
        )
    return result


# ── 3. 施工图审查标准 (CD items) ───────────────────────────


def get_construction_review_params() -> List[Dict[str, Any]]:
    """返回 30 条 CD 审查项的结构化参数（P92 后端数据源）"""
    result = []
    for item in CONSTRUCTION_REVIEW_ITEMS:
        result.append(
            {
                "item_id": item.item_id,
                "category": item.category,
                "major": item.major,
                "title": item.title,
                "description": item.description,
                "standard_ref": item.standard_ref,
                "level": item.level,
                "check_method": item.check_method,
                "func_id": item.func_id,
                "weight": item.weight,
            }
        )
    return result


# ── 4. 审查样本导出（来自 review_history DB）────────────


def get_review_samples(
    limit: int = 50,
    review_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    从审查历史数据库提取（输入特征 → 判定结果 → 判定依据）三元组。
    供 SFT 微调使用。数据源：SQLite review_history 表。
    """
    samples = []
    try:
        from src.api.review.review_history import list_review_history

        history = list_review_history(limit=limit, offset=0)
        tasks = history.get("items", history.get("data", []))
        if isinstance(history, dict) and "data" in history and "items" not in history:
            tasks = history["data"]
        if not isinstance(tasks, list):
            tasks = []

        tasks.sort(key=lambda t: t.get("created_at", t.get("reviewedAt", "")), reverse=True)
        for task in tasks[:limit]:
            if review_id and task.get("task_id", task.get("id")) != review_id:
                continue
            samples.append(_extract_sample(task))
    except Exception as _e:
        logger.warning("[P120] 审查历史读取失败，返回空样本集: %s: %s", type(_e).__name__, _e)
    return samples


def _extract_sample(task: Dict[str, Any]) -> Dict[str, Any]:
    """从一条 review task 提取 SFT 样本"""
    task_id = task.get("task_id", task.get("id", ""))
    drawing_name = task.get("drawing_name", task.get("drawingName", ""))
    status = task.get("status", "")
    summary = task.get("summary", {})
    details = task.get("details", [])
    corrections = task.get("corrections", [])

    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(details, list):
        details = []
    if not isinstance(corrections, list):
        corrections = []

    # 构建输入特征描述
    features = {
        "drawing_name": drawing_name,
        "total_checks": summary.get("total_checks", 0),
        "total_entities": summary.get("total_entities", 0),
        "violations": summary.get("violations", len(details)),
        "building_type": task.get("building_type", task.get("buildingType", "")),
        "standard": task.get("standard", ""),
        "score": summary.get("score", 0),
        "status": status,
    }

    # 构建每条违规的判定记录（SFT 三元组）
    decisions = []
    for d in details:
        decisions.append(
            {
                "input_features": {
                    "entity_id": d.get("entity_id", ""),
                    "entity_type": d.get("entity_type", ""),
                    "func_id": d.get("func_id", ""),
                    "clause_id": d.get("clause_id", ""),
                    "extracted_value": d.get("extracted_value", ""),
                    "required_value": d.get("required_value", ""),
                    "difference": d.get("difference", ""),
                    "confidence": d.get("confidence", 0),
                },
                "output_label": "FAIL",
                "rationale": d.get("explanation", d.get("violation", "")),
                "standard_ref": d.get("clause_id", ""),
                "suggestion": next(
                    (
                        c.get("suggestion", c.get("description", ""))
                        for c in corrections
                        if c.get("entity_id") == d.get("entity_id")
                    ),
                    "",
                ),
            }
        )

    # 如果有修正建议也作为正例样本
    for c in corrections:
        decisions.append(
            {
                "input_features": {
                    "entity_id": c.get("entity_id", ""),
                    "clause_id": c.get("clause_id", ""),
                    "func_id": c.get("func_id", ""),
                },
                "output_label": "PASS_AFTER_FIX",
                "rationale": c.get("suggestion", c.get("description", "")),
                "standard_ref": c.get("clause_id", ""),
                "suggestion": "",
            }
        )

    return {
        "task_id": task_id,
        "input_features": features,
        "decisions": decisions,
        "metadata": {
            "created_at": task.get("created_at", task.get("reviewedAt", "")),
            "drawing_name": drawing_name,
            "total_decisions": len(decisions),
        },
    }


# ── 5. 空间关系图（placeholder，需 P92 数据源）──────────


def get_spatial_graph(review_id: str) -> Dict[str, Any]:
    """
    从指定 review 中提取空间关系（节点 + 边 + 几何属性）。
    P93: 待 task_queue 补充 review 的空间关系数据后实现。
    当前返回占位结构。
    """
    # TODO: 从 review 结果中提取 room/wall/door/stair 的 bbox 和邻接关系
    return {
        "review_id": review_id,
        "nodes": [],
        "edges": [],
        "note": "spatial_graph 需要从 review 结果中解析 room/wall/door/stair 几何数据，待后续实现",
    }


# ── 6. 格式转换 ───────────────────────────────────────────


def to_sft_jsonl(
    functions: List[Dict[str, Any]],
    layer_rules: List[Dict[str, Any]],
    cd_items: List[Dict[str, Any]],
) -> str:
    """
    转换为 SFT JSONL 格式（Qwen/DeepSeek 兼容）：
    每条一条规则一个 prompt-response 对。
    """
    lines = []
    for func in functions:
        user_content = (
            f"判断以下原子函数的规则是否合理：\n"
            f"函数ID: {func['func_id']}\n"
            f"名称: {func['title']}\n"
            f"描述: {func['description']}\n"
            f"操作: {func['operator']} {func['threshold']} {func['unit']}\n"
            f"目标实体: {func['target_entities']}\n"
            f"条款: {func['clause_id']}"
        )
        assistant_content = (
            f"规则判定：该原子函数用于检查 {func['title']}，"
            f"操作为 {func['operator']} {func['threshold']} {func['unit']}，"
            f"目标实体类型包括 {func['target_entities']}，"
            f"依赖关系为 {func['depends_on']}，"
            f"全局上下文需求: {func['requires_global_context']}。"
            f"该规则符合 {func['clause_id']} 条款要求。"
        )
        line = json.dumps(
            {
                "messages": [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": assistant_content},
                ],
                "metadata": {
                    "source": "atomic_functions",
                    "category": func["category"],
                    "func_id": func["func_id"],
                },
            },
            ensure_ascii=False,
        )
        lines.append(line)

    # 添加 LAYER_RULES 样本
    for rule in layer_rules:
        line = json.dumps(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": f"判断图层 '{rule['pattern']}' 应该被分类为哪种实体类型？",
                    },
                    {
                        "role": "assistant",
                        "content": f"图层 '{rule['pattern']}' 应分类为 {rule['entity_type']}（匹配方式: {rule['match_type']}，来源: {rule['source']}）。",
                    },
                ],
                "metadata": {
                    "source": "layer_rules",
                    "pattern": rule["pattern"],
                    "entity_type": rule["entity_type"],
                },
            },
            ensure_ascii=False,
        )
        lines.append(line)

    # 添加 CD 审查项样本
    for item in cd_items:
        line = json.dumps(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": f"判断施工图审查项 '{item['title']}' 的 {item['category']} 是否符合 {item['standard_ref']} 要求？",
                    },
                    {
                        "role": "assistant",
                        "content": f"审查项 {item['item_id']}：{item['title']}，"
                        f"描述: {item['description']}，"
                        f"规范依据: {item['standard_ref']}，"
                        f"深度等级: {item['level']}，"
                        f"检查方式: {item['check_method']}。",
                    },
                ],
                "metadata": {
                    "source": "construction_review",
                    "item_id": item["item_id"],
                    "major": item["major"],
                    "level": item["level"],
                },
            },
            ensure_ascii=False,
        )
        lines.append(line)

    return "\n".join(lines)


def to_hf_dataset_description(
    functions: List[Dict[str, Any]],
    layer_rules: List[Dict[str, Any]],
    cd_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    返回 HuggingFace Dataset 格式的描述。
    兼容 datasets.load_dataset() 直接加载。
    """
    return {
        "dataset_info": {
            "dataset_name": "BAA_construction_review_params",
            "description": "BAA 施工图审查模型参数数据集，包含原子函数规则、图层语义映射、施工图审查标准",
            "config_name": "full",
            "version": "1.0.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "features": {
            "atomic_functions": {
                "count": len(functions),
                "fields": {
                    "func_id": "string",
                    "title": "string",
                    "category": "string",
                    "clause_id": "string",
                    "description": "string",
                    "operator": "string",
                    "threshold": "float",
                    "unit": "string",
                    "target_entities": "list[string]",
                    "depends_on": "list[string]",
                    "requires_global_context": "bool",
                    "check_method": "string",
                },
            },
            "layer_rules": {
                "count": len(layer_rules),
                "fields": {
                    "pattern": "string",
                    "entity_type": "string",
                    "source": "string",
                    "priority": "int",
                    "match_type": "string",
                },
            },
            "construction_review_items": {
                "count": len(cd_items),
                "fields": {
                    "item_id": "string",
                    "category": "string",
                    "major": "string",
                    "title": "string",
                    "description": "string",
                    "standard_ref": "string",
                    "level": "string",
                    "check_method": "string",
                    "func_id": "string",
                    "weight": "float",
                },
            },
        },
        "data_files": {
            "atomic_functions": functions,
            "layer_rules": layer_rules,
            "construction_review_items": cd_items,
        },
    }
