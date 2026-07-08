"""P41 LLM 修正建议引擎测试"""

import json
import os
from unittest.mock import patch, MagicMock

import pytest
from src.baa_engine.llm_correction import (
    LLMCorrectionEngine,
    CorrectionSuggestion,
)

# ── 测试数据 ──────────────────────────────────────────────

SAMPLE_FINDING = {
    "entity_id": "stair_001",
    "entity_type": "staircase",
    "clause_id": "GB50016-5.5.18",
    "clause_title": "疏散楼梯净宽",
    "extracted_value": 1.0,
    "required_value": 1.2,
    "difference": -0.2,
    "explanation": "疏散楼梯净宽度1.0m，需要≥1.2m",
}

SAMPLE_FINDINGS = [
    SAMPLE_FINDING,
    {
        "entity_id": "door_001",
        "entity_type": "fire_door",
        "clause_id": "GB50016-6.5.1",
        "clause_title": "防火门等级",
        "extracted_value": 1.0,
        "required_value": 3.0,
        "difference": -2.0,
        "explanation": "防火门等级不足",
    },
]

SAMPLE_LLM_RESPONSE = json.dumps(
    {
        "action": "resize",
        "description": "疏散楼梯净宽不足",
        "recommendation": "将楼梯宽度从1.0m加宽至1.2m，需增加0.2m。建议扩宽梯段或调整相邻房间布局。",
        "parameters": {"target_width": 1.2, "increase_by": 0.2},
    }
)


# ── TestLLMCorrectionEngine ───────────────────────────────


class TestLLMCorrectionEngine:
    def test_init_defaults(self):
        engine = LLMCorrectionEngine()
        assert engine.mode == "hybrid"
        assert engine.timeout == 30
        assert engine.cache_size == 50

    def test_init_with_env_vars(self):
        os.environ["BAA_CORRECTION_MODE"] = "rule"
        os.environ["BAA_LLM_ENDPOINT"] = "http://test:8000/v1"
        engine = LLMCorrectionEngine()
        assert engine.mode == "rule"
        assert engine.llm_endpoint == "http://test:8000/v1"
        del os.environ["BAA_CORRECTION_MODE"]
        del os.environ["BAA_LLM_ENDPOINT"]

    def test_init_with_params(self):
        engine = LLMCorrectionEngine(
            mode="llm",
            llm_endpoint="http://custom:8000/v1",
            api_key="test-key",
            timeout=60,
            cache_size=10,
        )
        assert engine.mode == "llm"
        assert engine.llm_endpoint == "http://custom:8000/v1"
        assert engine.api_key == "test-key"
        assert engine.timeout == 60
        assert engine.cache_size == 10

    def test_rule_mode(self):
        """规则模式返回与现有 CorrectionEngine 一致的结果"""
        engine = LLMCorrectionEngine(mode="rule")
        suggestions = engine.generate(SAMPLE_FINDINGS, [])
        assert len(suggestions) > 0
        for s in suggestions:
            assert s.source == "rule"
            assert s.recommendation != ""

    def test_rule_mode_no_findings(self):
        engine = LLMCorrectionEngine(mode="rule")
        suggestions = engine.generate([], [])
        assert suggestions == []

    def test_llm_mode_no_api_key(self):
        """无 API key 时 LLM 模式应返回空列表"""
        engine = LLMCorrectionEngine(mode="llm", api_key="")
        suggestions = engine.generate(SAMPLE_FINDINGS, [])
        assert suggestions == []

    def test_llm_mode_with_mocked_api(self):
        """LLM 模式 mock API 返回"""
        engine = LLMCorrectionEngine(
            mode="llm",
            api_key="test-key",
            llm_endpoint="http://mock:8000/v1",
        )
        with patch("httpx.Client") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": SAMPLE_LLM_RESPONSE}}]
            }
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            suggestions = engine.generate(SAMPLE_FINDINGS[:1], [])
        assert len(suggestions) == 1
        assert suggestions[0].source == "llm"
        assert suggestions[0].action == "resize"
        assert "1.0m" in suggestions[0].recommendation

    def test_llm_mode_api_timeout(self):
        """API 超时应返回空列表"""
        engine = LLMCorrectionEngine(
            mode="llm",
            api_key="test-key",
            llm_endpoint="http://mock:8000/v1",
            timeout=1,
        )
        with patch("httpx.Client") as mock_client:
            from httpx import TimeoutException

            mock_client.return_value.__enter__.return_value.post.side_effect = TimeoutException(
                "timeout"
            )
            suggestions = engine.generate(SAMPLE_FINDINGS[:1], [])
        assert suggestions == []

    def test_llm_mode_api_error(self):
        """API 异常应返回空列表"""
        engine = LLMCorrectionEngine(
            mode="llm",
            api_key="test-key",
            llm_endpoint="http://mock:8000/v1",
        )
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = Exception(
                "connection error"
            )
            suggestions = engine.generate(SAMPLE_FINDINGS[:1], [])
        assert suggestions == []

    def test_hybrid_mode_no_api_key(self):
        """无 API key 时 hybrid 模式应回退到规则引擎"""
        engine = LLMCorrectionEngine(mode="hybrid", api_key="")
        suggestions = engine.generate(SAMPLE_FINDINGS, [])
        assert len(suggestions) > 0
        for s in suggestions:
            assert s.source == "rule"

    def test_hybrid_mode_with_mocked_api(self):
        """hybrid 模式 mock API 返回"""
        engine = LLMCorrectionEngine(
            mode="hybrid",
            api_key="test-key",
            llm_endpoint="http://mock:8000/v1",
        )
        with patch("httpx.Client") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": SAMPLE_LLM_RESPONSE}}]
            }
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            suggestions = engine.generate(SAMPLE_FINDINGS[:1], [])
        assert len(suggestions) == 1
        assert suggestions[0].source == "hybrid"

    def test_hybrid_mode_llm_fallback(self):
        """LLM 失败时 hybrid 模式应回退到规则引擎"""
        engine = LLMCorrectionEngine(
            mode="hybrid",
            api_key="test-key",
            llm_endpoint="http://mock:8000/v1",
        )
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = Exception("error")
            suggestions = engine.generate(SAMPLE_FINDINGS[:1], [])
        assert len(suggestions) == 1
        assert suggestions[0].source == "rule"

    def test_generate_for_result(self):
        engine = LLMCorrectionEngine(mode="rule")
        review_result = {"findings": SAMPLE_FINDINGS}
        output = engine.generate_for_result(review_result)
        assert len(output) > 0
        assert "entity_id" in output[0]
        assert "recommendation" in output[0]
        assert "priority" in output[0]
        assert "source" in output[0]

    def test_generate_for_result_empty(self):
        engine = LLMCorrectionEngine(mode="rule")
        output = engine.generate_for_result({"findings": []})
        assert output == []

    def test_cache(self):
        """相同缓存键应复用结果"""
        engine = LLMCorrectionEngine(
            mode="llm",
            api_key="test-key",
            llm_endpoint="http://mock:8000/v1",
        )
        with patch("httpx.Client") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": SAMPLE_LLM_RESPONSE}}]
            }
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            # 第一次调用
            s1 = engine.generate(SAMPLE_FINDINGS[:1], [])
            # 第二次调用（应命中缓存，不调用 API）
            s2 = engine.generate(SAMPLE_FINDINGS[:1], [])
        assert len(s1) == len(s2) == 1
        assert s1[0].recommendation == s2[0].recommendation

    def test_cache_clear(self):
        engine = LLMCorrectionEngine(mode="rule")
        engine._cache = {"key1": {}, "key2": {}}
        engine.clear_cache()
        assert len(engine._cache) == 0

    def test_cache_eviction(self):
        engine = LLMCorrectionEngine(mode="rule", cache_size=2)
        engine._add_to_cache("k1", {"data": 1})
        engine._add_to_cache("k2", {"data": 2})
        assert len(engine._cache) == 2
        engine._add_to_cache("k3", {"data": 3})
        assert len(engine._cache) == 2
        assert "k1" not in engine._cache


# ── TestPromptBuilding ────────────────────────────────────


class TestPromptBuilding:
    def test_build_prompt(self):
        engine = LLMCorrectionEngine()
        prompt = engine._build_prompt(SAMPLE_FINDING, [])
        assert "GB50016-5.5.18" in prompt
        assert "疏散楼梯净宽" in prompt
        assert "staircase" in prompt
        assert "JSON" in prompt
        assert "recommendation" in prompt

    def test_build_prompt_with_rule_suggestion(self):
        engine = LLMCorrectionEngine()
        suggestion = CorrectionSuggestion(
            entity_id="stair_001",
            clause_id="GB50016-5.5.18",
            recommendation="测试建议",
        )
        prompt = engine._build_prompt(SAMPLE_FINDING, [], rule_suggestion=suggestion)
        assert "测试建议" in prompt
        assert "优化" in prompt

    def test_build_prompt_empty_finding(self):
        engine = LLMCorrectionEngine()
        prompt = engine._build_prompt({}, [])
        assert prompt is not None
        assert len(prompt) > 50


# ── TestParseResponse ────────────────────────────────────


class TestParseResponse:
    def test_parse_valid_json(self):
        engine = LLMCorrectionEngine()
        result = engine._parse_llm_response(SAMPLE_LLM_RESPONSE)
        assert result is not None
        assert result["action"] == "resize"
        assert "疏散楼梯" in result["description"]

    def test_parse_markdown_wrapped(self):
        engine = LLMCorrectionEngine()
        wrapped = f"```json\n{SAMPLE_LLM_RESPONSE}\n```"
        result = engine._parse_llm_response(wrapped)
        assert result is not None
        assert result["action"] == "resize"

    def test_parse_markdown_no_label(self):
        engine = LLMCorrectionEngine()
        wrapped = f"```\n{SAMPLE_LLM_RESPONSE}\n```"
        result = engine._parse_llm_response(wrapped)
        assert result is not None
        assert result["action"] == "resize"

    def test_parse_text_with_surrounding(self):
        engine = LLMCorrectionEngine()
        text = f"这里是思考过程。\n{SAMPLE_LLM_RESPONSE}\n以上是建议。"
        result = engine._parse_llm_response(text)
        assert result is not None
        assert result["action"] == "resize"

    def test_parse_missing_fields(self):
        engine = LLMCorrectionEngine()
        incomplete = json.dumps({"action": "resize"})
        result = engine._parse_llm_response(incomplete)
        assert result is not None
        assert result["description"] == ""
        assert result["recommendation"] == ""
        assert result["parameters"] == {}

    def test_parse_empty(self):
        engine = LLMCorrectionEngine()
        result = engine._parse_llm_response("")
        assert result is None

    def test_parse_invalid_json(self):
        engine = LLMCorrectionEngine()
        result = engine._parse_llm_response("这不是 JSON")
        assert result is None

    def test_parse_partial_brace(self):
        engine = LLMCorrectionEngine()
        text = '前文 {"action": "resize", "description": "test"} 后文'
        result = engine._parse_llm_response(text)
        assert result is not None
        assert result["action"] == "resize"

    def test_parse_none(self):
        engine = LLMCorrectionEngine()
        result = engine._parse_llm_response(None)
        assert result is None


# ── TestPriority ─────────────────────────────────────────


class TestPriority:
    def test_high_for_add_action(self):
        engine = LLMCorrectionEngine()
        s = CorrectionSuggestion(action="ADD")
        assert engine._calc_priority(s) == "high"

    def test_high_for_replace_action(self):
        engine = LLMCorrectionEngine()
        s = CorrectionSuggestion(action="REPLACE")
        assert engine._calc_priority(s) == "high"

    def test_high_for_large_delta(self):
        engine = LLMCorrectionEngine()
        s = CorrectionSuggestion(action="resize", delta=0.6, required_value=1.0)
        assert engine._calc_priority(s) == "high"

    def test_medium_for_medium_delta(self):
        engine = LLMCorrectionEngine()
        s = CorrectionSuggestion(action="resize", delta=0.3, required_value=1.0)
        assert engine._calc_priority(s) == "medium"

    def test_low_for_small_delta(self):
        engine = LLMCorrectionEngine()
        s = CorrectionSuggestion(action="resize", delta=0.1, required_value=1.0)
        assert engine._calc_priority(s) == "low"

    def test_low_no_threshold(self):
        engine = LLMCorrectionEngine()
        s = CorrectionSuggestion(action="resize", delta=0.5, required_value=0)
        assert engine._calc_priority(s) == "low"
