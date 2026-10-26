"""T-D2 尺度参数注入 + 硬编码阈值兜底 单元测试。

覆盖 DoD：
1. SpecRepository.get_threshold_safe：找不到 clause 或 params.threshold=0.0 → None
2. ScaleContext：代理 StandardSet + scale_overrides 接口预留
3. SpecRepository.get_threshold 旧路径零破坏（直接 import 行为不变）

关键背景：atomic/fire_general/*.py 里 198 个 AtomicFunction 带 threshold=数字硬编码，
admin_routes.py Step 3 循环无条件覆盖 func.threshold 为 get_threshold 返回值——
当 clause 缺失或 params.threshold=0.0 时返回 (0.0, '', '>=')，
导致原子函数阈值被毁（16 个住宅类 clause + 128 个无 clause 函数全失效）。
"""

import pytest

from src.baa_engine.spec_data._repo import SpecRepository
from src.baa_engine.standards import (
    StandardSet,
    ScaleContext,
    build_func_standard_maps_for_all_sets,
)


# ── Fixture ──────────────────────────────────────────────


@pytest.fixture
def repo():
    return SpecRepository()


@pytest.fixture
def cn_set(repo):
    build_func_standard_maps_for_all_sets(repo.list_all())
    return ScaleContext.create("CN-National-v1")


# ── 1. get_threshold_safe 返回 None 的三种情况 ─────────


def test_safe_missing_clause_returns_none(repo):
    """SpecRepository 根本没有这条 clause → None。"""
    assert repo.get_threshold_safe("NONEXISTENT-999", "civil", "GB 50016-2014") is None


def test_safe_zero_threshold_returns_none(repo):
    """clause.params.threshold = 0.0 → None（16 个 GB50067/GB50974 住宅类 clause
    填了 clause 但 threshold=0.0 是数据填漏，不应被当作有效阈值覆盖原子函数硬编码）。"""
    # 找一个 repo 里 threshold=0 的 clause
    zero_clause = None
    for c in repo.list_all():
        if isinstance(c.params, dict) and float(c.params.get("threshold", 1)) == 0.0:
            zero_clause = c
            break
    if zero_clause is None:
        pytest.skip("当前 repo 无 threshold=0 的 clause（数据已修正）")
    result = repo.get_threshold_safe(
        zero_clause.clause_id, "civil", zero_clause.standard
    )
    assert result is None, f"期望 None，实得 {result}"


# 注意：不做"修改 clause.params 删 threshold key"测试——SpecRepository 共享
# gb50016_core/__init__.py 的 INITIAL_CLAUSES 全局 list，修改会污染后续所有测试。
# get_threshold 里已做 .get('threshold') 安全取值，遇到缺失 key 自动回默认。


# ── 2. get_threshold_safe 有正常值 → 返回 tuple ─────────


def test_safe_valid_threshold(repo):
    """GB50016-5.5.18（疏散走道宽度 ≥1.2m）有正常 threshold=1.2 → 返回 (1.2, 'm', '>=')。"""
    val, unit, op = repo.get_threshold_safe(
        "GB50016-5.5.18", "civil", "GB 50016-2014"
    )
    assert val == 1.2
    assert unit == "m"
    assert op == ">="


def test_safe_default_standard_fallback(repo):
    """standard=None → 自动回退默认 GB 50016-2014。"""
    result = repo.get_threshold_safe("GB50016-5.5.18", "civil")
    assert result is not None
    val, _, _ = result
    assert val == 1.2


# ── 3. ScaleContext 代理 StandardSet ─────────────────────


def test_scale_context_resolve_standard(cn_set):
    """ScaleContext.create('CN-National-v1') 后 resolve_standard 代理 StandardSet。"""
    assert cn_set.standard_set is not None
    resolved = cn_set.resolve_standard("DIM-001")  # 疏散走道 func
    assert resolved == "GB 50016-2014"


def test_scale_context_unknown_code_graceful():
    """未知 code → ScaleContext.standard_set=None，resolve_standard 返回 None。"""
    ctx = ScaleContext.create("XX-NOTEXIST")
    assert ctx.standard_set is None
    assert ctx.resolve_standard("DIM-001") is None
    assert ctx.get_override("GB50016-5.5.18", "civil") is None


# ── 4. scale_overrides 接口预留 ─────────────────────────


def test_scale_overrides_priority(repo):
    """get_override 返回地标覆盖阈值（预留接口，未来 D1-T3 地标填入）。

    ScaleContext.scale_overrides 优先级 > SpecRepository > 原子函数硬编码。
    """
    ctx = ScaleContext.create("CN-National-v1")
    # 空 scale_overrides 时返回 None
    assert ctx.get_override("GB50016-5.5.18", "civil") is None

    # 地标覆盖：假设上海地标把疏散宽度从 1.2m 提到 1.5m
    ctx.scale_overrides["GB50016-5.5.18"] = {"civil": 1.5, "industrial": 1.8}
    assert ctx.get_override("GB50016-5.5.18", "civil") == 1.5
    assert ctx.get_override("GB50016-5.5.18", "industrial") == 1.8


# ── 5. 回归保护：旧 get_threshold 零破坏 ────────────────


def test_get_threshold_legacy_unmodified(repo):
    """旧 SpecRepository.get_threshold(...) 不传 standard 参数时
    必须维持原有默认 "GB 50016-2014" 行为，零破坏存量。"""
    val1, u1, op1 = repo.get_threshold("GB50016-5.5.18", "civil")
    val2, u2, op2 = repo.get_threshold_safe(
        "GB50016-5.5.18", "civil", "GB 50016-2014"
    )
    assert val1 == val2 == 1.2
    assert u1 == u2 == "m"
    assert op1 == op2 == ">="


def test_get_threshold_legacy_fallback_zero(repo):
    """旧 get_threshold 找不到 clause 时仍返回 (0.0, '', '>=')——
    原有调用方（如 admin_routes.py 另一条手动阈值查询）不做修改。"""
    val, u, op = repo.get_threshold("NONEXISTENT", "civil")
    assert val == 0.0
    assert u == ""
    assert op == ">="
