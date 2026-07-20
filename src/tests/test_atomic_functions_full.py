"""
P11: 原子函数全量单元测试 — 覆盖所有 390 个函数 ID

覆盖策略：
- 每个函数：PASS / FAIL / BOUNDARY / WRONG_ENTITY 四种场景
- 注入 _test_value 精确控制 _extract_value 返回值，无需穷举 property 映射
- 生产环境 entity 不含 _test_value，不受影响
"""

import pytest
from src.baa_engine.atomic_functions import (
    AtomicFunction,
    FuncCategory,
    FuncRegistry,
    FuncResult,
)

from src.baa_engine.atomic import ATOMIC_FUNCTIONS


def make_entity(type_name: str, **props) -> dict:
    return {"id": "E-001", "type": type_name, "properties": props}


# ── Registry 初始化 ──────────────────────────────────────

REGISTRY = FuncRegistry()
for func in ATOMIC_FUNCTIONS:
    REGISTRY.register(func)


# ── 备选 entity type 池，用于 WRONG_ENTITY ─────────────────

ENTITY_TYPE_POOL = [
    "staircase",
    "room",
    "door",
    "window",
    "wall",
    "corridor",
    "hydrant",
    "pump",
    "detector",
    "smoke_vent",
    "elevator",
    "fire_wall",
    "parking_space",
    "sign",
    "handrail",
    "pipe",
    "conduit",
    "speaker",
    "alarm_panel",
    "bathroom",
]


# ── helper：生成参数集 ────────────────────────────────────


def _pick_wrong_type(good_types: list) -> str:
    """从 ENTITY_TYPE_POOL 中选一个不在 good_types 中的 type。"""
    good = set(good_types)
    for t in ENTITY_TYPE_POOL:
        if t not in good:
            return t
    # 兜底：构造一个肯定不在的
    return f"_wrong_{good_types[0]}"


def _param_cases():
    """为每个原子函数生成 PASS/FAIL/BOUNDARY/WRONG_ENTITY 四个参数。"""
    cases = []
    for func in ATOMIC_FUNCTIONS:
        fid = func.func_id
        op = func.operator
        thr = func.threshold
        te = func.target_entities  # 已归一化为 list

        # ── PASS/FAIL 值 ───────────────────────────────────
        # thr=0 特殊处理：常规比例缩放会得到 0，与边界值无区分度
        if thr == 0:
            if op in (">=", ">", "=="):
                pass_val, fail_val = 1.0, -1.0
            else:  # <=, <
                pass_val, fail_val = -1.0, 1.0
        elif op in (">=", ">"):
            pass_val = thr * 1.1  # 明显大于阈值
            fail_val = thr * 0.9  # 明显小于阈值
        elif op == "==":
            pass_val = thr  # 精确等于
            fail_val = thr * 2.0  # 明显不等于
        else:  # <=, <
            pass_val = thr * 0.9  # 明显小于阈值
            fail_val = thr * 1.1  # 明显大于阈值

        # thr=0 时 BOUNDARY 仍用 thr=0，>= / <= 通过，> / < 不通过
        boundary_expected = "PASS" if op in (">=", "==", "<=") else "FAIL"

        # ── PASS ───────────────────────────────────────────
        entity = make_entity(te[0] if te else "unknown", _test_value=pass_val)
        cases.append((fid, "PASS", entity, "PASS"))

        # ── FAIL ───────────────────────────────────────────
        entity = make_entity(te[0] if te else "unknown", _test_value=fail_val)
        cases.append((fid, "FAIL", entity, "FAIL"))

        # ── BOUNDARY ───────────────────────────────────────
        entity = make_entity(te[0] if te else "unknown", _test_value=thr)
        cases.append((fid, "BOUNDARY", entity, boundary_expected))

        # ── WRONG_ENTITY ───────────────────────────────────
        if te:
            wrong_type = _pick_wrong_type(te)
            entity = make_entity(wrong_type, _test_value=pass_val)
            cases.append((fid, "WRONG_ENTITY", entity, None))
        # te=[] 的函数不生成 WRONG_ENTITY（matches() 返回 True）

    return cases


# ── 测试类 ────────────────────────────────────────────────


class TestAtomicFunctionsFull:
    """全量原子函数测试：每个 ID 覆盖 PASS/FAIL/BOUNDARY/WRONG_ENTITY"""

    @pytest.mark.parametrize(
        "func_id,scenario,entity,expected",
        _param_cases(),
        ids=[f"{fid}-{sc}" for fid, sc, _, _ in _param_cases()],
    )
    def test_atomic_function(self, func_id, scenario, entity, expected):
        func = REGISTRY.get(func_id)
        assert func is not None, f"{func_id} not in registry"
        result = func.execute(entity)

        if scenario == "WRONG_ENTITY":
            assert result is None, f"{func_id}: expected None for wrong entity"
        else:
            assert result is not None, f"{func_id}: expected result for {scenario}"
            assert (
                result.result == expected
            ), f"{func_id} {scenario}: got {result.result}, expected {expected}"

    def test_registry_count(self):
        """验证注册表包含所有 390 个函数"""
        count = REGISTRY.count
        assert count == len(
            ATOMIC_FUNCTIONS
        ), f"Registry has {count} functions, expected {len(ATOMIC_FUNCTIONS)}"
        assert count >= 390, f"Expected >= 390 functions, got {count}"

    def test_all_ids_unique(self):
        """所有 func_id 唯一"""
        ids = [f.func_id for f in ATOMIC_FUNCTIONS]
        assert len(ids) == len(set(ids)), "Duplicate func_ids found"

    def test_all_ids_registered(self):
        """所有 func_id 都在 registry 中"""
        for func in ATOMIC_FUNCTIONS:
            assert REGISTRY.get(func.func_id) is not None
