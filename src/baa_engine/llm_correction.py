"""
BAA LLM 驱动的修正建议生成器（P41 新增）

基于审查违规结果，使用 LLM 生成更智能的修正方案。
支持三种模式：
- rule: 纯规则引擎（与现有行为一致）
- llm: 纯 LLM 生成
- hybrid: 规则引擎优先 + LLM 补充优化

配置：
- 环境变量 BAA_CORRECTION_MODE: rule / llm / hybrid
- 环境变量 BAA_LLM_ENDPOINT: OpenAI 兼容 API 端点
- 环境变量 BAA_LLM_API_KEY: API 密钥
- 环境变量 BAA_LLM_MODEL: 模型名称（默认 deepseek-chat）
"""

import json
import os
import hashlib
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# ── 默认配置 ──────────────────────────────────────────────

DEFAULT_MODE = "hybrid"
DEFAULT_LLM_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_LLM_MODEL = "deepseek-chat"
DEFAULT_LLM_TIMEOUT = 30
DEFAULT_CACHE_SIZE = 50


@dataclass
class CorrectionSuggestion:
    """修正建议数据结构（与 correction_engine 的 CorrectionSuggestion 兼容）"""

    entity_id: str = ""
    entity_type: str = ""
    clause_id: str = ""
    clause_title: str = ""
    action: str = "modify"
    description: str = ""
    current_value: float = 0.0
    required_value: float = 0.0
    delta: float = 0.0
    recommendation: str = ""
    parameters: Dict = field(default_factory=dict)
    source: str = "rule"


class LLMCorrectionEngine:
    """LLM 驱动的修正建议生成器"""

    MODE_RULE = "rule"
    MODE_LLM = "llm"
    MODE_HYBRID = "hybrid"

    def __init__(
        self,
        mode: str = None,
        llm_endpoint: str = None,
        api_key: str = None,
        llm_model: str = None,
        timeout: int = DEFAULT_LLM_TIMEOUT,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ):
        self.mode = mode or os.environ.get("BAA_CORRECTION_MODE", DEFAULT_MODE)
        self.llm_endpoint = llm_endpoint or os.environ.get("BAA_LLM_ENDPOINT", DEFAULT_LLM_ENDPOINT)
        self.api_key = api_key or os.environ.get("BAA_LLM_API_KEY", "")
        self.llm_model = llm_model or os.environ.get("BAA_LLM_MODEL", DEFAULT_LLM_MODEL)
        self.timeout = timeout
        self.cache_size = cache_size
        self._cache: Dict[str, Dict] = {}
        self._rule_engine = None

    @property
    def rule_engine(self):
        """延迟初始化规则引擎（避免循环导入）"""
        if self._rule_engine is None:
            from src.baa_engine.correction_engine import CorrectionEngine

            self._rule_engine = CorrectionEngine()
        return self._rule_engine

    def generate(
        self, findings: List[Dict], entities: List[Dict], mode: str = None
    ) -> List[CorrectionSuggestion]:
        effective_mode = mode or self.mode
        if effective_mode == self.MODE_RULE:
            return self._generate_rule(findings, entities)
        elif effective_mode == self.MODE_LLM:
            return self._generate_llm(findings, entities)
        elif effective_mode == self.MODE_HYBRID:
            return self._generate_hybrid(findings, entities)
        logger.warning(f"未知模式 {effective_mode}，回退到 rule")
        return self._generate_rule(findings, entities)

    def generate_for_result(self, review_result: dict, mode: str = None) -> List[Dict]:
        """从 /review 返回结果生成修正建议（用于API返回）"""
        findings = review_result.get("findings", [])
        # P65: 透传 entities 给 LLM 模式，支撑空间上下文分析
        entities = review_result.get("entities", [])
        suggestions = self.generate(findings, entities, mode=mode)
        output = []
        for s in suggestions:
            output.append(
                {
                    "entity_id": s.entity_id,
                    "entity_type": s.entity_type,
                    "clause_id": s.clause_id,
                    "clause_title": s.clause_title,
                    "action": s.action,
                    "description": s.description,
                    "recommendation": s.recommendation,
                    "parameters": s.parameters,
                    "priority": self._calc_priority(s),
                    "source": s.source,
                }
            )
        return output

    # ── 三种模式实现 ──────────────────────────────────────

    def _generate_rule(self, findings, entities) -> List[CorrectionSuggestion]:
        raw = self.rule_engine.generate(findings, entities)
        suggestions = []
        for r in raw:
            suggestions.append(
                CorrectionSuggestion(
                    entity_id=r.entity_id,
                    entity_type=r.entity_type,
                    clause_id=r.clause_id,
                    clause_title=r.clause_title,
                    action=r.action.value,
                    description=r.description,
                    current_value=r.current_value,
                    required_value=r.required_value,
                    delta=r.delta,
                    recommendation=r.recommendation,
                    parameters=r.parameters,
                    source="rule",
                )
            )
        return suggestions

    def _generate_llm(self, findings, entities) -> List[CorrectionSuggestion]:
        suggestions = []
        for finding in findings:
            cache_key = self._get_cache_key(finding)
            cached = self._cache.get(cache_key)
            if cached:
                suggestions.append(self._dict_to_suggestion(cached))
                continue
            prompt = self._build_prompt(finding, entities)
            # P65: LLM 调用失败时降级到最小化建议，保证可用性
            response = self._call_llm(prompt)
            if response is None:
                # 纯 LLM 模式无规则引擎备选：生成最小化描述并 append
                fallback = CorrectionSuggestion(
                    entity_id=finding.get("entity_id", ""),
                    entity_type=finding.get("entity_type", ""),
                    clause_id=finding.get("clause_id", ""),
                    clause_title=finding.get("clause_title", ""),
                    action="modify",
                    description=finding.get(
                        "explanation", f"{finding.get('clause_title', '')}违规"
                    ),
                    current_value=finding.get("extracted_value", 0),
                    required_value=finding.get("required_value", 0),
                    delta=finding.get("difference", 0),
                    recommendation=f"{finding.get('clause_title', '')}不满足{finding.get('clause_id', '')}要求，请参照规范整改。",
                    parameters={},
                    source="rule_fallback",
                )
                suggestions.append(fallback)
                continue
            parsed = self._parse_llm_response(response)
            if parsed is None:
                continue
            parsed["entity_id"] = finding.get("entity_id", "")
            parsed["entity_type"] = finding.get("entity_type", "")
            parsed["clause_id"] = finding.get("clause_id", "")
            parsed["clause_title"] = finding.get("clause_title", "")
            parsed["source"] = "llm"
            parsed["current_value"] = parsed.get("current_value", finding.get("extracted_value", 0))
            parsed["required_value"] = parsed.get(
                "required_value", finding.get("required_value", 0)
            )
            parsed["delta"] = parsed.get("delta", finding.get("difference", 0))
            self._add_to_cache(cache_key, parsed)
            suggestions.append(self._dict_to_suggestion(parsed))
        return suggestions

    def _generate_hybrid(self, findings, entities) -> List[CorrectionSuggestion]:
        rule_suggestions = self._generate_rule(findings, entities)
        result = []
        for i, suggestion in enumerate(rule_suggestions):
            finding = findings[i] if i < len(findings) else {}
            cache_key = self._get_cache_key(finding)
            cached = self._cache.get(cache_key)
            if cached:
                llm_s = self._dict_to_suggestion(cached)
                llm_s.source = "hybrid"
                result.append(llm_s)
                continue
            prompt = self._build_prompt(finding, entities, rule_suggestion=suggestion)
            response = self._call_llm(prompt)
            if response:
                parsed = self._parse_llm_response(response)
                if parsed:
                    parsed["entity_id"] = finding.get("entity_id", suggestion.entity_id)
                    parsed["entity_type"] = finding.get("entity_type", suggestion.entity_type)
                    parsed["clause_id"] = finding.get("clause_id", suggestion.clause_id)
                    parsed["clause_title"] = finding.get("clause_title", suggestion.clause_title)
                    parsed["source"] = "hybrid"
                    parsed["current_value"] = parsed.get("current_value", suggestion.current_value)
                    parsed["required_value"] = parsed.get(
                        "required_value", suggestion.required_value
                    )
                    parsed["delta"] = parsed.get("delta", suggestion.delta)
                    self._add_to_cache(cache_key, parsed)
                    result.append(self._dict_to_suggestion(parsed))
                    continue
            result.append(suggestion)
        return result

    # ── LLM 调用 ──────────────────────────────────────────

    def _build_prompt(self, finding, entities, rule_suggestion=None) -> str:
        clause_id = finding.get("clause_id", "")
        clause_title = finding.get("clause_title", "")
        entity_type = finding.get("entity_type", "")
        extracted = finding.get("extracted_value", "N/A")
        required = finding.get("required_value", "N/A")
        difference = finding.get("difference", "N/A")
        explanation = finding.get("explanation", "")
        target_id = finding.get("entity_id", "")

        # ── P65: 空间上下文注入 ──────────────────────────────
        # 收集与违规实体在同一 bbox 区域的其他实体，构建局部空间描述
        spatial_context = self._extract_spatial_context(entities, target_id, entity_type)

        prompt = (
            f"你是一个建筑图纸审查的修正建议专家。请根据以下违规信息，"
            f"结合图纸空间上下文，生成具体、可操作的修正建议。\n\n"
            f"## 违规信息\n"
            f"- 规范条款: {clause_id} {clause_title}\n"
            f"- 违规实体类型: {entity_type}\n"
            f"- 违规实体ID: {target_id}\n"
            f"- 检测值: {extracted}\n"
            f"- 要求值: {required}\n"
            f"- 偏差: {difference}\n"
            f"- 违规说明: {explanation}\n"
        )

        if spatial_context:
            prompt += (
                f"\n## 空间上下文（局部图纸环境）\n"
                f"{spatial_context}\n\n"
                f"请结合空间上下文，考虑修正方案对周边实体的影响。\n"
            )

        if rule_suggestion:
            prompt += (
                f"\n## 规则引擎已生成建议\n"
                f"{rule_suggestion.recommendation}\n\n"
                f"请优化上述建议，使其更具体、更可操作，并结合空间上下文。\n"
            )
        prompt += (
            "\n## 输出要求\n"
            "请以 JSON 格式返回，包含以下字段：\n"
            '- "action": 修正操作类型（resize/add/replace/relocate/seal/upgrade/enlarge/modify）\n'
            '- "description": 问题描述（中文，一句话）\n'
            '- "recommendation": 具体修正建议（中文，详细、可操作，包含具体数值和步骤）\n'
            '- "parameters": 修正参数（dict，如 {"target_width": 1.2, "increase_by": 0.3}）\n\n'
            "## 示例输出\n"
            "```json\n"
            "{\n"
            '    "action": "resize",\n'
            '    "description": "疏散楼梯净宽不足",\n'
            '    "recommendation": "将楼梯宽度从1.0m加宽至1.2m，需增加0.2m。建议扩宽梯段或调整相邻房间布局。",\n'
            '    "parameters": {"target_width": 1.2, "increase_by": 0.2}\n'
            "}\n"
            "```\n\n"
            "请只输出 JSON，不要包含其他文字。"
        )
        return prompt

    def _extract_spatial_context(self, entities, target_id, target_type):
        """从 entities 中提取与违规实体相关的空间上下文。

        只描述局部环境，避免 prompt 过长。限制最多 8 个邻域实体。
        """
        if not entities:
            return ""
        # 找到目标实体的 bbox
        target_bbox = None
        for e in entities:
            if (
                str(e.get("id", "")).strip() == str(target_id).strip()
                and e.get("type") == target_type
            ):
                target_bbox = e.get("bbox")
                break
        if not target_bbox:
            return ""
        tx1, ty1, tx2, ty2 = target_bbox
        tx_c, ty_c = (tx1 + tx2) / 2, (ty1 + ty2) / 2
        tw, th = tx2 - tx1, ty2 - ty1
        # 邻域扩展 2 倍目标尺寸，限定只收集邻近实体
        margin_x = max(tw, 2.0)
        margin_y = max(th, 2.0)
        neighbors = []
        for e in entities:
            if e.get("type") == target_type:
                continue  # 排除同类型（目标自身）
            bbox = e.get("bbox")
            if not bbox:
                continue
            ex1, ey1, ex2, ey2 = bbox
            ex_c = (ex1 + ex2) / 2
            ey_c = (ey1 + ey2) / 2
            if abs(ex_c - tx_c) > margin_x or abs(ey_c - ty_c) > margin_y:
                continue
            label = e.get("label") or e.get("name") or ""
            neighbors.append((e.get("type", ""), label, (ex_c - tx_c, ey_c - ty_c)))
        if not neighbors:
            return "无邻近实体。"
        # 按距离排序，取最近 8 个
        neighbors.sort(key=lambda n: abs(n[2][0]) + abs(n[2][1]))
        neighbors = neighbors[:8]
        lines = []
        for typ, label, (dx, dy) in neighbors:
            desc = f"- {typ}"
            if label:
                desc += f" ({label})"
            direction = ""
            if abs(dx) > abs(dy):
                direction = "东侧" if dx > 0 else "西侧"
            else:
                direction = "北侧" if dy > 0 else "南侧"
            desc += f"，位于{direction}约{max(abs(dx), abs(dy)):.1f}m"
            lines.append(desc)
        return "\n".join(lines)

    def _call_llm(self, prompt: str) -> Optional[str]:
        if not self.api_key:
            logger.warning("LLM API key 未配置，跳过 LLM 调用")
            return None
        try:
            with httpx.Client(timeout=self.timeout) as client:
                payload = {
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 1024,
                }
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                resp = client.post(self.llm_endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            logger.warning(f"LLM 调用超时（{self.timeout}s）")
            return None
        except Exception as e:
            logger.warning(f"LLM 调用失败: {e}")
            return None

    def _parse_llm_response(self, response: str) -> Optional[Dict]:
        if not response:
            return None
        text = response.strip()
        # 去除 markdown 代码块包裹
        if text.startswith("```"):
            start = text.find("\n")
            if start != -1:
                text = text[start:].strip()
            if text.endswith("```"):
                text = text[:-3].strip()
            elif "```" in text:
                text = text.rsplit("```", 1)[0].strip()
        # 解析 JSON
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                try:
                    data = json.loads(text[brace_start : brace_end + 1])
                except json.JSONDecodeError:
                    return None
            else:
                return None
        if not isinstance(data, dict):
            return None
        data.setdefault("action", "modify")
        data.setdefault("description", "")
        data.setdefault("recommendation", "")
        data.setdefault("parameters", {})
        return data

    # ── 缓存 ──────────────────────────────────────────────

    def _get_cache_key(self, finding: Dict) -> str:
        clause_id = finding.get("clause_id", "")
        entity_type = finding.get("entity_type", "")
        raw = f"{clause_id}:{entity_type}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _add_to_cache(self, key: str, value: Dict):
        if len(self._cache) >= self.cache_size:
            first_key = next(iter(self._cache))
            del self._cache[first_key]
        self._cache[key] = value

    def clear_cache(self):
        self._cache.clear()

    # ── 工具方法 ──────────────────────────────────────────

    def _dict_to_suggestion(self, d: Dict) -> CorrectionSuggestion:
        return CorrectionSuggestion(
            entity_id=d.get("entity_id", ""),
            entity_type=d.get("entity_type", ""),
            clause_id=d.get("clause_id", ""),
            clause_title=d.get("clause_title", ""),
            action=d.get("action", "modify"),
            description=d.get("description", ""),
            current_value=d.get("current_value", 0.0),
            required_value=d.get("required_value", 0.0),
            delta=d.get("delta", 0.0),
            recommendation=d.get("recommendation", ""),
            parameters=d.get("parameters", {}),
            source=d.get("source", "rule"),
        )

    def _calc_priority(self, s: CorrectionSuggestion) -> str:
        """计算修正优先级（与 CorrectionEngine._calc_priority 兼容）"""
        urgent_actions = {"ADD", "REPLACE", "UPGRADE", "add", "replace", "upgrade"}
        if s.action in urgent_actions:
            return "high"
        if s.delta > 0 and s.required_value > 0 and s.delta > s.required_value * 0.5:
            return "high"
        if s.delta > 0 and s.required_value > 0 and s.delta > s.required_value * 0.2:
            return "medium"
        return "low"
