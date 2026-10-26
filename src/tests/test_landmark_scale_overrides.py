"""T-D3 首批地标（上海/广东）单元测试。

覆盖 DoD：
1. CN-Shanghai-v1 / CN-Guangdong-v1 注册到位
2. ScaleContext.create 深拷贝 StandardSet.scale_overrides（不污染全局）
3. 三级兜底完整链路：地标 scale_overrides > SpecRepository > 硬编码
4. 同图双跑 diff JSON：CN-National vs CN-Shanghai → 阈值变更检测
"""

import copy

import pytest

from src.baa_engine.spec_data._repo import SpecRepository
from src.baa_engine.standards import (
    StandardSet,
    ScaleContext,
    available_codes,
    build_func_standard_maps_for_all_sets,
    load_set,
)


@pytest.fixture
def repo():
    r = SpecRepository()
    build_func_standard_maps_for_all_sets(r.list_all())
    return r


# ── 1. 地标集注册 ────────────────────────────────────────


def test_shanghai_set_registered():
    """CN-Shanghai-v1 已注册，scale_overrides 有 3 条覆盖。"""
    s = load_set("CN-Shanghai-v1")
    assert s.name == "中国 上海地方标准（v1）"
    assert len(s.scale_overrides) == 3
    assert "GB50016-5.5.18-2" in s.scale_overrides
    assert s.scale_overrides["GB50016-5.5.18-2"]["civil"] == 1.2


def test_guangdong_set_registered():
    """CN-Guangdong-v1 已注册，scale_overrides 有 3 条覆盖。"""
    s = load_set("CN-Guangdong-v1")
    assert s.name == "中国 广东地方标准（v1）"
    assert len(s.scale_overrides) == 3
    # 广东商业主通道 ≥3m
    assert s.scale_overrides["GB50016-5.5.18-2"]["civil"] == 3.0
    assert s.scale_overrides["GB50016-5.5.17"]["civil"] == 25.0


def test_shanghai_included_standards_are_gb():
    """地标 included_standards 仍是国标——地标只做阈值覆盖不新增 standard。"""
    s = load_set("CN-Shanghai-v1")
    assert "GB 50016-2014" in s.included_standards
    # 不应该有任何 "DGJ" 开头的地标 standard
    assert not any("DGJ" in std or "DBJ" in std for std in s.included_standards)


# ── 2. ScaleContext 深拷贝 ────────────────────────────────


def test_scale_context_deepcopy_landmark_overrides():
    """ScaleContext.create 深拷贝 StandardSet.scale_overrides，
    实例内修改不污染全局注册数据。"""
    ctx = ScaleContext.create("CN-Shanghai-v1")
    # 修改实例
    ctx.scale_overrides["GB50016-7.1.1"]["civil"] = 99.0
    ctx.scale_overrides["NEW-FAKE"] = {"civil": 0.0}
    # 全局注册数据不应被污染
    orig = StandardSet.get("CN-Shanghai-v1")
    assert orig.scale_overrides["GB50016-7.1.1"]["civil"] == 4.5  # 原值
    assert "NEW-FAKE" not in orig.scale_overrides


def test_scale_context_national_has_no_overrides():
    """CN-National-v1 无 scale_overrides → ScaleContext.scale_overrides 为 {}。"""
    ctx = ScaleContext.create("CN-National-v1")
    assert ctx.scale_overrides == {}
    # 未知 code 也为 {}
    ctx2 = ScaleContext.create("XX-UNKNOWN")
    assert ctx2.scale_overrides == {}


# ── 3. 三级兜底完整链路 ──────────────────────────────────


def test_tier1_landmark_override_takes_priority(repo):
    """三级兜底：scale_overrides(地标) > SpecRepository(国标) > 硬编码。
    上海地标覆盖 GB50016-5.5.18-2（走道）为国标 1.1m → 地标 1.2m。"""
    ctx = ScaleContext.create("CN-Shanghai-v1")
    clause_id = "GB50016-5.5.18-2"
    bt = "civil"
    std = ctx.resolve_standard("DIM-001") or "GB 50016-2014"

    # 模拟 admin_routes.py Step 3 三级兜底
    override = ctx.get_override(clause_id, bt)
    safe = repo.get_threshold_safe(clause_id, bt, std)

    if override is not None:
        final = override
        source = "landmark"
    elif safe is not None:
        final = safe[0]
        source = "spec_repo"
    else:
        final = 1.1  # 硬编码兜底
        source = "hardcoded"

    assert final == 1.2
    assert source == "landmark"
    # 验证国标值仍在 SpecRepository 里（没被地标污染）
    assert safe[0] == 1.1


def test_tier2_spec_repo_used_when_no_landmark_override(repo):
    """三级兜底：地标无覆盖 → SpecRepository 取值。
    CN-Shanghai 对 GB50016-5.5.17（疏散距离）无覆盖 → 应走国标 30m。"""
    ctx = ScaleContext.create("CN-Shanghai-v1")
    clause_id = "GB50016-5.5.17"
    bt = "civil"
    std = ctx.resolve_standard("DIST-001") or "GB 50016-2014"

    override = ctx.get_override(clause_id, bt)
    safe = repo.get_threshold_safe(clause_id, bt, std)

    assert override is None  # 上海地标不覆盖疏散距离
    assert safe is not None
    assert safe[0] == 30.0  # 国标值
    # SpecRepository 被用于最终阈值
    final = override if override is not None else safe[0]
    assert final == 30.0


# ── 4. 同图双跑 diff JSON ────────────────────────────────


def test_same_func_different_standard_sets_produce_diff(repo):
    """同一张图纸（模拟）用 CN-National vs CN-Shanghai → 关键 clause
    阈值不同 → diff JSON 输出正确。"""
    target_clauses = ["GB50016-5.5.18-2", "GB50016-5.5.18", "GB50016-7.1.1"]

    def _resolve_threshold(clause_id: str, standard_set_code: str) -> dict:
        """模拟 admin_routes.py Step 3 的三级兜底，返回 {threshold, source}。"""
        ctx = ScaleContext.create(standard_set_code)
        bt = "civil"
        std = ctx.resolve_standard("DIM-001") or "GB 50016-2014"

        override = ctx.get_override(clause_id, bt)
        safe = repo.get_threshold_safe(clause_id, bt, std)

        if override is not None:
            return {"threshold": override, "source": "landmark"}
        elif safe is not None:
            return {"threshold": safe[0], "source": "spec_repo"}
        else:
            return {"threshold": 0.0, "source": "hardcoded"}

    # 跑两套标准集
    diff = []
    for cid in target_clauses:
        nat = _resolve_threshold(cid, "CN-National-v1")
        sha = _resolve_threshold(cid, "CN-Shanghai-v1")
        if nat["threshold"] != sha["threshold"]:
            diff.append({
                "clause_id": cid,
                "national": nat["threshold"],
                "national_source": nat["source"],
                "shanghai": sha["threshold"],
                "shanghai_source": sha["source"],
                "delta": round(sha["threshold"] - nat["threshold"], 3),
            })

    assert len(diff) == 3  # 3 条 clause 全变
    # 走道：1.1m → 1.2m，+0.1m
    corridor = [d for d in diff if d["clause_id"] == "GB50016-5.5.18-2"][0]
    assert corridor["national"] == 1.1
    assert corridor["shanghai"] == 1.2
    assert corridor["delta"] == 0.1
    # 楼梯：1.2m → 1.3m，+0.1m
    stair = [d for d in diff if d["clause_id"] == "GB50016-5.5.18"][0]
    assert stair["national"] == 1.2
    assert stair["shanghai"] == 1.3
    # 消防车道：4.0m → 4.5m，+0.5m
    lane = [d for d in diff if d["clause_id"] == "GB50016-7.1.1"][0]
    assert lane["national"] == 4.0
    assert lane["shanghai"] == 4.5
    assert lane["delta"] == 0.5

    # CN-Guangdong vs CN-National 也有 diff
    diff2 = []
    for cid in target_clauses + ["GB50016-5.5.17", "GB50016-5.5.18-3"]:
        nat = _resolve_threshold(cid, "CN-National-v1")
        gd = _resolve_threshold(cid, "CN-Guangdong-v1")
        if nat["threshold"] != gd["threshold"]:
            diff2.append({"clause_id": cid, "nat": nat["threshold"], "gd": gd["threshold"]})

    # 广东走道 3.0m 是最大差异
    gd_corridor = [d for d in diff2 if d["clause_id"] == "GB50016-5.5.18-2"][0]
    assert gd_corridor["gd"] == 3.0
    assert gd_corridor["nat"] == 1.1
