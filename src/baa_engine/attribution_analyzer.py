"""
BAA 归因分析模块 - 三要素 + 注意力热力图（规则版）
"""

from typing import Dict, Any, List  # typing: generic type hints
from dataclasses import dataclass  # dataclasses: @dataclass decorator
import uuid  # uuid: unique ID generation


@dataclass  # definition: immutable dataclass
class Finding:  # definition: violation finding record
    """违规判定（完整归因）"""

    finding_id: str  # 操作
    clause: Dict[str, Any]  # 规范依据
    extracted_params: Dict[str, Any]  # 参数证据
    judgement: Dict[str, Any]  # 判定逻辑
    attention_map: Dict[str, Any]  # 注意力热力图
    explanation: str  # 说明
    suggestion: str  # 修改建议


class AttributionAnalyzer:  # definition: attribution analysis engine
    """归因分析引擎（规则版）"""

    def build_finding(  # method: build complete violation finding
        self,  # 解包
        func_result: Any,  # 操作
        clause: Dict[str, Any],  # 操作
        entity: Dict[str, Any],  # 操作
        related_entities: List[Dict[str, Any]] = None,  # 操作
    ) -> Finding:  # return type: Finding dataclass
        """构建完整违规判定（三要素+热力图）"""

        # 要素一：规范依据
        clause_info = {  # dict: extract clause metadata
            "standard": clause.get("standard", ""),  # 字段
            "clause_id": clause.get("clause_id", ""),  # 字段
            "title": clause.get("title", ""),  # 字段
            "text": clause.get("text", ""),  # 字段
            "category": clause.get("category", ""),  # 字段
        }  # dict end: clause_info

        # 要素二：参数证据
        params = {  # dict: extract parameter evidence
            "entity_id": entity.get("id", ""),  # 字段
            "entity_type": entity.get("type", ""),  # 字段
            "property_name": func_result.params.get("extracted_key", "value"),  # 字段
            "extracted_value": func_result.actual,  # 字段
            "unit": func_result.params.get("unit", ""),  # 字段
            "extraction_method": "ezdxf_dimension_extraction",  # 字段
            "confidence": entity.get("confidence", 0.9),  # 字段
        }  # dict end: params

        # 要素三：判定逻辑
        judgement = {  # dict: extract judgement result
            "operator": func_result.operator,  # 字段
            "threshold": func_result.threshold,  # 字段
            "actual": func_result.actual,  # 字段
            "result": func_result.result,  # 字段
            "delta": func_result.delta,  # 字段
            "severity": func_result.severity.value,  # 字段
        }  # dict end: judgement

        # 附加：注意力热力图
        attention = self._compute_attention(  # call: compute attention heatmap
            entity, related_entities or []  # 解包
        )  # call end: _compute_attention

        # 生成说明+建议
        explanation = self._build_explanation(
            clause_info, params, judgement
        )  # call: build explanation text
        suggestion = self._build_suggestion(
            clause_info, params, judgement
        )  # call: build suggestion text

        return Finding(  # return: construct Finding object
            finding_id=f"BAA-{uuid.uuid4().hex[:8].upper()}",  # field: unique finding ID
            clause=clause_info,  # field: clause reference
            extracted_params=params,  # field: extracted parameters
            judgement=judgement,  # field: judgement result
            attention_map=attention,  # field: attention heatmap
            explanation=explanation,  # field: human explanation
            suggestion=suggestion,  # field: fix suggestion
        )  # return end

    def _compute_attention(  # method: compute rule-based attention
        self,  # 解包
        target_entity: Dict[str, Any],  # 操作
        related_entities: List[Dict[str, Any]],  # 操作
    ) -> Dict[str, Any]:  # return type: attention dict
        """规则化注意力热力图"""
        focus_areas = []  # init: collect focus areas

        # 目标实体权重最高
        focus_areas.append(
            {  # dict: add target entity with highest weight
                "entity_id": target_entity.get("id", ""),  # 字段
                "entity_type": target_entity.get("type", ""),  # 字段
                "weight": 0.87,  # 字段
                "reason": "目标实体（判定对象）",  # 字段
            }
        )  # dict end: target focus area

        # 直接关联实体
        for entity in related_entities:  # 循环
            weight = 0.12 / max(
                len(related_entities), 1
            )  # calc: distribute remaining weight across related entities
            focus_areas.append(
                {  # dict: add related entity focus area
                    "entity_id": entity.get("id", ""),  # 字段
                    "entity_type": entity.get("type", ""),  # 字段
                    "weight": round(weight, 2),  # 字段
                    "reason": f"关联实体（{entity.get('type', '')}）",  # 字段
                }
            )  # dict end: related focus area

        # 归一化
        total = sum(a["weight"] for a in focus_areas)  # calc: sum all weights for normalization
        for area in focus_areas:  # 循环
            area["weight"] = round(area["weight"] / total, 2)  # 操作

        return {  # return: attention map structure
            "type": "rule_based",  # 字段
            "focus_areas": focus_areas,  # 字段
            "explanation": f"模型重点关注了{target_entity.get('id', '')}（{target_entity.get('type', '')}，注意力权重{focus_areas[0]['weight']}）",  # 字段
        }  # return end

    def _build_explanation(  # method: build human-readable explanation
        self,  # 解包
        clause: Dict[str, Any],  # 操作
        params: Dict[str, Any],  # 操作
        judgement: Dict[str, Any],  # 操作
    ) -> str:  # return type: explanation string
        """生成说明"""
        if judgement["result"] == "PASS":  # branch: pass case returns positive explanation
            return (
                f"{params.get('entity_type', '')}{params.get('entity_id', '')}的"  # string: build pass explanation
                f"{params.get('property_name', '')}为{params.get('extracted_value', '')}"  # 操作
                f"{params.get('unit', '')}，"  # 操作
                f"满足{clause.get('standard', '')}第{clause.get('clause_id', '')}条要求"  # 操作
                f"（{clause.get('text', '')}），"  # 操作
                f"预期{judgement.get('operator', '')} {judgement.get('threshold', '')}{params.get('unit', '')}，"  # 操作
                f"实际{params.get('extracted_value', '')}{params.get('unit', '')}，判定通过。"
            )  # 操作

        return (
            f"{params.get('entity_type', '')}{params.get('entity_id', '')}的"  # string: build failure explanation with delta
            f"{params.get('property_name', '')}为{params.get('extracted_value', '')}"  # 操作
            f"{params.get('unit', '')}，"  # 操作
            f"不满足{clause.get('standard', '')}第{clause.get('clause_id', '')}条要求"  # 操作
            f"（{clause.get('text', '')}），"  # 操作
            f"预期{judgement.get('operator', '')} {judgement.get('threshold', '')}{params.get('unit', '')}，"  # 操作
            f"实际{params.get('extracted_value', '')}{params.get('unit', '')}，"  # 操作
            f"差值为{abs(judgement.get('delta', 0)):.2f}{params.get('unit', '')}。"
        )  # 操作

    def _build_suggestion(  # method: build actionable fix suggestion
        self,  # 解包
        clause: Dict[str, Any],  # 操作
        params: Dict[str, Any],  # 操作
        judgement: Dict[str, Any],  # 操作
    ) -> str:  # return type: suggestion string
        """生成修改建议"""
        if judgement["result"] == "PASS":  # branch: pass case needs no fix
            return "无需修改。"  # return: no action needed

        operator = judgement.get("operator", "")  # extract: comparison operator from judgement
        threshold = judgement.get("threshold", 0)  # extract: threshold value from judgement
        unit = params.get("unit", "")  # extract: measurement unit from params

        if operator in (">=", ">"):  # branch: >= or > requires increase
            return (
                f"建议将{params.get('entity_type', '')}{params.get('entity_id', '')}的"  # string: build increase suggestion
                f"{params.get('property_name', '')}增加至≥{threshold}{unit}，"  # 操作
                f"或调整布局以满足要求。"
            )  # 操作
        elif operator in ("<=", "<"):  # 分支
            return (
                f"建议将{params.get('entity_type', '')}{params.get('entity_id', '')}的"  # string: build decrease suggestion
                f"{params.get('property_name', '')}减少至≤{threshold}{unit}。"
            )  # 操作
        else:  # 否则
            return (
                f"请检查{params.get('entity_type', '')}{params.get('entity_id', '')}的"  # string: build generic check suggestion
                f"{params.get('property_name', '')}设置，确保符合规范要求。"
            )  # 操作
