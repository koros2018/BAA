"""
BAA 归因分析模块 - 三要素 + 注意力热力图（规则版）
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import uuid


@dataclass
class Finding:
    """违规判定（完整归因）"""
    finding_id: str
    clause: Dict[str, Any]          # 规范依据
    extracted_params: Dict[str, Any] # 参数证据
    judgement: Dict[str, Any]       # 判定逻辑
    attention_map: Dict[str, Any]   # 注意力热力图
    explanation: str                # 说明
    suggestion: str                 # 修改建议


class AttributionAnalyzer:
    """归因分析引擎（规则版）"""

    def build_finding(
        self,  # 解包
        func_result: Any,
        clause: Dict[str, Any],
        entity: Dict[str, Any],
        related_entities: List[Dict[str, Any]] = None,
    ) -> Finding:
        """构建完整违规判定（三要素+热力图）"""

        # 要素一：规范依据
        clause_info = {  # 赋值
            "standard": clause.get("standard", ""),
            "clause_id": clause.get("clause_id", ""),
            "title": clause.get("title", ""),
            "text": clause.get("text", ""),
            "category": clause.get("category", ""),
        }

        # 要素二：参数证据
        params = {  # 赋值
            "entity_id": entity.get("id", ""),
            "entity_type": entity.get("type", ""),
            "property_name": func_result.params.get("extracted_key", "value"),
            "extracted_value": func_result.actual,
            "unit": func_result.params.get("unit", ""),
            "extraction_method": "ezdxf_dimension_extraction",
            "confidence": entity.get("confidence", 0.9),
        }

        # 要素三：判定逻辑
        judgement = {  # 赋值
            "operator": func_result.operator,
            "threshold": func_result.threshold,
            "actual": func_result.actual,
            "result": func_result.result,
            "delta": func_result.delta,
            "severity": func_result.severity.value,
        }

        # 附加：注意力热力图
        attention = self._compute_attention(  # 赋值
            entity, related_entities or []  # 解包
        )

        # 生成说明+建议
        explanation = self._build_explanation(clause_info, params, judgement)  # 赋值
        suggestion = self._build_suggestion(clause_info, params, judgement)  # 赋值

        return Finding(  # 返回
            finding_id=f"BAA-{uuid.uuid4().hex[:8].upper()}",  # 赋值
            clause=clause_info,  # 赋值
            extracted_params=params,  # 赋值
            judgement=judgement,  # 赋值
            attention_map=attention,  # 赋值
            explanation=explanation,  # 赋值
            suggestion=suggestion,  # 赋值
        )

    def _compute_attention(
        self,  # 解包
        target_entity: Dict[str, Any],
        related_entities: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """规则化注意力热力图"""
        focus_areas = []  # 赋值

        # 目标实体权重最高
        focus_areas.append({  # 调用
            "entity_id": target_entity.get("id", ""),
            "entity_type": target_entity.get("type", ""),
            "weight": 0.87,
            "reason": "目标实体（判定对象）",
        })

        # 直接关联实体
        for entity in related_entities:  # 循环
            weight = 0.12 / max(len(related_entities), 1)  # 赋值
            focus_areas.append({  # 调用
                "entity_id": entity.get("id", ""),
                "entity_type": entity.get("type", ""),
                "weight": round(weight, 2),
                "reason": f"关联实体（{entity.get('type', '')}）",
            })

        # 归一化
        total = sum(a["weight"] for a in focus_areas)  # 赋值
        for area in focus_areas:  # 循环
            area["weight"] = round(area["weight"] / total, 2)

        return {  # 返回
            "type": "rule_based",
            "focus_areas": focus_areas,
            "explanation": f"模型重点关注了{target_entity.get('id', '')}（{target_entity.get('type', '')}，注意力权重{focus_areas[0]['weight']}）",
        }

    def _build_explanation(
        self,  # 解包
        clause: Dict[str, Any],
        params: Dict[str, Any],
        judgement: Dict[str, Any],
    ) -> str:
        """生成说明"""
        if judgement["result"] == "PASS":  # 条件判断
            return (f"{params.get('entity_type', '')}{params.get('entity_id', '')}的"  # 返回
                    f"{params.get('property_name', '')}为{params.get('extracted_value', '')}"
                    f"{params.get('unit', '')}，"
                    f"满足{clause.get('standard', '')}第{clause.get('clause_id', '')}条要求"
                    f"（{clause.get('text', '')}），判定通过。")

        return (f"{params.get('entity_type', '')}{params.get('entity_id', '')}的"  # 返回
                f"{params.get('property_name', '')}为{params.get('extracted_value', '')}"
                f"{params.get('unit', '')}，"
                f"不满足{clause.get('standard', '')}第{clause.get('clause_id', '')}条要求"
                f"（{clause.get('text', '')}），"
                f"差值为{abs(judgement.get('delta', 0)):.2f}{params.get('unit', '')}。")

    def _build_suggestion(
        self,  # 解包
        clause: Dict[str, Any],
        params: Dict[str, Any],
        judgement: Dict[str, Any],
    ) -> str:
        """生成修改建议"""
        if judgement["result"] == "PASS":  # 条件判断
            return "无需修改。"  # 返回

        operator = judgement.get("operator", "")  # 赋值
        threshold = judgement.get("threshold", 0)  # 赋值
        unit = params.get("unit", "")  # 赋值

        if operator in (">=", ">"):  # 条件判断
            return (f"建议将{params.get('entity_type', '')}{params.get('entity_id', '')}的"  # 返回
                    f"{params.get('property_name', '')}增加至≥{threshold}{unit}，"
                    f"或调整布局以满足要求。")
        elif operator in ("<=", "<"):  # 分支
            return (f"建议将{params.get('entity_type', '')}{params.get('entity_id', '')}的"  # 返回
                    f"{params.get('property_name', '')}减少至≤{threshold}{unit}。")
        else:  # 否则
            return (f"请检查{params.get('entity_type', '')}{params.get('entity_id', '')}的"  # 返回
                    f"{params.get('property_name', '')}设置，确保符合规范要求。")