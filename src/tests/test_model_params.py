"""P93: 模型参数导出测试"""

import json
import pytest

from src.baa_engine.model_params import (
    get_function_params,
    get_layer_rules,
    get_construction_review_params,
    to_sft_jsonl,
    to_hf_dataset_description,
)
from src.baa_engine.atomic_functions import FuncRegistry


@pytest.fixture
def registry():
    return FuncRegistry()


# ── get_function_params ──────────────────────────────


class TestGetFunctionParams:
    def test_returns_list(self, registry):
        result = get_function_params(registry)
        assert isinstance(result, list)

    def test_nonempty(self, registry):
        result = get_function_params(registry)
        assert len(result) > 0

    def test_required_fields(self, registry):
        for item in get_function_params(registry):
            for k in ("func_id", "title", "category", "clause_id"):
                assert k in item

    def test_category_values(self, registry):
        cats = {i["category"] for i in get_function_params(registry)}
        assert "dim" in cats
        assert "exist" in cats


# ── get_layer_rules ──────────────────────────────────


class TestGetLayerRules:
    def test_returns_list(self):
        result = get_layer_rules()
        assert isinstance(result, list)

    def test_nonempty(self):
        assert len(get_layer_rules()) > 0

    def test_fields(self):
        for item in get_layer_rules()[:3]:
            for k in ("pattern", "entity_type", "source", "priority", "match_type"):
                assert k in item

    def test_has_both_sources(self):
        sources = {i["source"] for i in get_layer_rules()}
        assert "LAYER_RULES" in sources
        assert "SHORT_LAYER_RULES" in sources


# ── get_construction_review_params ──────────────────


class TestGetCDParams:
    def test_returns_list(self):
        result = get_construction_review_params()
        assert isinstance(result, list)

    def test_nonempty(self):
        assert len(get_construction_review_params()) > 0

    def test_fields(self):
        for item in get_construction_review_params():
            for k in ("item_id", "title", "level"):
                assert k in item


# ── to_sft_jsonl ─────────────────────────────────────


class TestSFTExport:
    def test_produces_jsonl_lines(self, registry):
        funcs = get_function_params(registry)
        lr = get_layer_rules()
        cd = get_construction_review_params()
        lines = to_sft_jsonl(funcs, lr, cd).splitlines()
        assert len(lines) > 0
        for line in lines:
            json.loads(line)  # valid JSON per line

    def test_line_contains_messages(self, registry):
        funcs = get_function_params(registry)
        lr = get_layer_rules()
        cd = get_construction_review_params()
        parsed = json.loads(to_sft_jsonl(funcs, lr, cd).splitlines()[0])
        assert "messages" in parsed


# ── to_hf_dataset_description ────────────────────────


class TestHFDataset:
    def test_produces_dict(self, registry):
        funcs = get_function_params(registry)
        lr = get_layer_rules()
        cd = get_construction_review_params()
        result = to_hf_dataset_description(funcs, lr, cd)
        assert isinstance(result, dict)
        assert "dataset_info" in result
