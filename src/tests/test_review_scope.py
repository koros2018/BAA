"""A 类止血：非平面图幅剔除非平面适用的疏散规则（EVAC-002/003/004）。"""

import pytest

from src.baa_engine.review_scope import (
    PLAN_ONLY_FUNC_IDS,
    filter_plan_only_func_ids,
    filter_plan_only_funcs,
    is_plan_scope,
    normalize_scope_mode,
    not_applicable_func_ids,
)


class _FakeFunc:
    def __init__(self, func_id):
        self.func_id = func_id


def test_normalize_scope_mode_defaults_to_plan():
    assert normalize_scope_mode(None) == "plan"
    assert normalize_scope_mode("") == "plan"
    assert normalize_scope_mode("invalid") == "plan"
    assert normalize_scope_mode("plan") == "plan"
    assert normalize_scope_mode("unknown") == "unknown"
    assert normalize_scope_mode("non_plan") == "non_plan"


def test_is_plan_scope():
    assert is_plan_scope("plan") is True
    assert is_plan_scope(None) is True  # 旧调用方无 sheet_type，保持历史行为
    assert is_plan_scope("unknown") is False
    assert is_plan_scope("non_plan") is False


def test_filter_plan_only_func_ids():
    ids = ["DIM-001", "EVAC-002", "EVAC-003", "EVAC-004", "AREA-001"]
    assert filter_plan_only_func_ids(ids, "plan") == ids
    assert filter_plan_only_func_ids(ids, None) == ids
    assert filter_plan_only_func_ids(ids, "unknown") == ["DIM-001", "AREA-001"]
    assert filter_plan_only_func_ids(ids, "non_plan") == ["DIM-001", "AREA-001"]


def test_filter_plan_only_funcs_preserves_order():
    funcs = [_FakeFunc("A"), _FakeFunc("EVAC-002"), _FakeFunc("B")]
    assert [f.func_id for f in filter_plan_only_funcs(funcs, "plan")] == [
        "A",
        "EVAC-002",
        "B",
    ]
    assert [f.func_id for f in filter_plan_only_funcs(funcs, "unknown")] == ["A", "B"]


def test_not_applicable_func_ids():
    assert not_applicable_func_ids("plan") == []
    assert not_applicable_func_ids(None) == []
    assert not_applicable_func_ids("unknown") == sorted(PLAN_ONLY_FUNC_IDS)


@pytest.mark.parametrize("scope", ["unknown", "non_plan"])
def test_evac_rules_are_not_applicable_off_plan(scope):
    ids = filter_plan_only_func_ids(list(PLAN_ONLY_FUNC_IDS), scope)
    assert ids == []
