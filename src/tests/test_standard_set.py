"""T-D1 标准集（StandardSet）抽象层单元测试。

覆盖 DoD：
- list_sets / load_set 注册与加载
- populate_func_standard_map / resolve_standard 映射填充
- get_threshold standard=None 回退
- 未知 code 抛 KeyError

T-D1 为薄过滤层——不持有 SpecRepository、不破坏存量行为。
"""

import pytest

from src.baa_engine.standards import (
    StandardSet,
    build_func_standard_maps_for_all_sets,
    list_sets,
    load_set,
    available_codes,
)
from src.baa_engine.spec_data._repo import SpecRepository


# ── Fixture：每次用 SpecRepository 新实例，避免全局状态污染 ──


@pytest.fixture
def repo():
    return SpecRepository()


# ── 1. 内置集注册与加载 ─────────────────────────────────


def test_builtin_sets_registered():
    """内置集必须注册到位（CN-National-v1 + US-NFPA-v1）。"""
    codes = available_codes()
    assert "CN-National-v1" in codes
    assert "US-NFPA-v1" in codes
    assert len(codes) == 2


def test_load_set_cn_national():
    """CN-National-v1 加载成功，included_standards 覆盖 4 国标。"""
    s = load_set("CN-National-v1")
    assert s.code == "CN-National-v1"
    assert "GB 50016-2014" in s.included_standards
    assert "GB 50974-2014" in s.included_standards
    assert "GB 50763-2012" in s.included_standards
    assert "GB 50067-2014" in s.included_standards


def test_list_sets_sorted():
    """list_sets 按 code 排序返回。"""
    sets = list_sets()
    codes = [s.code for s in sets]
    assert codes == sorted(codes)


# ── 2. 未知 code 抛 KeyError ───────────────────────────


def test_load_set_unknown_keyerror():
    """未知 code 抛 KeyError，消息含可用值列表。"""
    with pytest.raises(KeyError) as exc:
        load_set("XX-NOTEXIST")
    msg = str(exc.value)
    assert "XX-NOTEXIST" in msg
    assert "CN-National-v1" in msg  # 可用值列表必须列出


# ── 3. 映射填充 + resolve_standard ─────────────────────


def test_populate_func_standard_map(repo):
    """SpecRepository + 标准集 → 能给 func_id 解析出 standard。"""
    assert repo.count > 0
    build_func_standard_maps_for_all_sets(repo.list_all())

    cn = load_set("CN-National-v1")
    # DIM-001 在 GB 50016-2014 有 clause（gb50016_core）
    # 映射后必须能 resolve
    assert cn.resolve_standard("DIM-001") == "GB 50016-2014"

    # ACCESS-001 仅在国标（GB 50974）有，NFPA 不含 → resolve 必须 None
    us = load_set("US-NFPA-v1")
    assert us.resolve_standard("ACCESS-001") is None
    # CN 集里 ACCESS-001 必须能 resolve 到某国标
    assert cn.resolve_standard("ACCESS-001") is not None


def test_resolve_standard_none_for_outside(repo):
    """标准集 included_standards 覆盖不到的 func 返回 None，
    由调用方（_run_review_task）回退到默认 standard。"""
    build_func_standard_maps_for_all_sets(repo.list_all())
    cn = load_set("CN-National-v1")
    # 造一个 repo 里没有的 func_id
    assert cn.resolve_standard("NONEXIST-FUNC-999") is None


# ── 4. get_threshold standard=None 回退 ─────────────────


def test_get_threshold_standard_none_fallback(repo):
    """T-D1 改 SpecRepository.get_threshold 后 standard=None 必须回退默认
    并拿到正常值，不抛异常、不返回全零。"""
    val, unit, op = repo.get_threshold("GB50016-5.5.18", "civil", None)
    assert val > 0
    assert unit
    assert op


def test_get_threshold_resolved_standard_equivalent_to_default(repo):
    """StandardSet.resolve_standard(GB50016-5.5.18 → GB 50016-2014)
    传入后结果与默认值一致（证明 resolve 链路打通）。"""
    build_func_standard_maps_for_all_sets(repo.list_all())
    cn = load_set("CN-National-v1")

    # 默认 standard
    val1, unit1, op1 = repo.get_threshold("GB50016-5.5.18", "civil")
    # 通过 StandardSet resolve 后的 standard
    sample = repo.get("GB50016-5.5.18", "GB 50016-2014")
    resolved = cn.resolve_standard(sample.func_id) if sample else None
    val2, unit2, op2 = repo.get_threshold("GB50016-5.5.18", "civil", resolved)
    assert val1 == val2
    assert unit1 == unit2
    assert op1 == op2


# ── 5. 存量回归（D1-T1 不破坏任何既有路径） ────────────


def test_direct_spec_repo_usage_unchanged(repo):
    """直接 import SpecRepository 调用 get_threshold 不传 standard
    必须维持旧行为（默认 GB 50016-2014）。"""
    val, unit, op = repo.get_threshold("GB50016-5.5.18", "civil")
    assert val == 1.2  # 基线：GB50016-5.5.18 疏散走道 ≥1.2m
    assert unit == "m"
    assert op == ">="


def test_direct_clause_imports_unchanged():
    """spec_data 子模块的条款列表仍能直接 import（_repo 未被破坏）。"""
    from src.baa_engine.spec_data import (
        INITIAL_CLAUSES,
        GB50016_CLAUSES,
        GB50974_CLAUSES,
        GB50763_CLAUSES,
        GB50067_CLAUSES,
        NFPA_CLAUSES,
    )

    assert len(INITIAL_CLAUSES) > 0
    assert len(GB50016_CLAUSES) > 0
    assert len(GB50974_CLAUSES) > 0
    assert len(GB50763_CLAUSES) > 0
    assert len(GB50067_CLAUSES) > 0
    assert len(NFPA_CLAUSES) > 0
