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


# ── AREA 类守卫专项测试 ──────────────────────────────────────


class TestAreaGuards:
    """AREA 类原子函数的误报治理守卫专项测试。

    验证 atomic_functions.py 通用 AREA 分支的多层守卫是否正确：
    1. 适用性质守（人口密度、面积比）
    2. 特化 subtype 守卫（普通 room 不触发特化 AREA 规则）
    3. target_entities 语义修正（fire_elevator ≠ 前室）
    4. bbox 兜底白名单 + 合理性检查
    """

    @staticmethod
    def _entity(type_name: str, subtype: str = "", area_m2=None, area=None,
                bbox=None, **props) -> dict:
        ent = {"id": "E-001", "type": type_name}
        if subtype:
            ent["subtype"] = subtype
        if bbox:
            ent["bbox"] = bbox
        p = dict(props)
        if area_m2 is not None:
            p["area_m2"] = area_m2
        if area is not None:
            p["area"] = area
        ent["properties"] = p
        return ent

    def _val(self, func_id: str, entity: dict):
        func = REGISTRY.get(func_id)
        return func._extract_value(entity)

    # ── 守卫 1：人口密度 AREA-020 无 people → None ───────────

    def test_area020_no_people(self):
        """AREA-020（5.0人/m²）无人口数据 → None"""
        ent = self._entity("room", area_m2=100.0)
        assert self._val("AREA-020", ent) is None

    def test_area020_with_people(self):
        """AREA-020 有 people → 返回密度"""
        ent = self._entity("room", area_m2=100.0, people=200)
        assert self._val("AREA-020", ent) == pytest.approx(2.0)

    # ── 守卫 2：面积比 AREA-011/017 → 单窗实体无 floor_area → None ─

    def test_area011_window_returns_none(self):
        """AREA-011 排烟窗比 → 单 window 无地面面积 → None"""
        ent = self._entity("window", area_m2=0.5)
        assert self._val("AREA-011", ent) is None

    def test_area017_window_returns_none(self):
        """AREA-017 同 AREA-011 → None"""
        ent = self._entity("window", area_m2=0.5)
        assert self._val("AREA-017", ent) is None

    # ── 守卫 3：特化 subtype 守卫 ────────────────────────────────

    def test_area004_normal_room_returns_none(self):
        """AREA-004（30㎡ 消防控制室）普通 room → None"""
        ent = self._entity("room", subtype="", area_m2=50.0)
        assert self._val("AREA-004", ent) is None

    def test_area004_control_room_works(self):
        """AREA-004 control_room 正常 → 返回面积"""
        ent = self._entity("room", subtype="control_room", area_m2=50.0)
        assert self._val("AREA-004", ent) == pytest.approx(50.0)

    def test_area006_normal_room_returns_none(self):
        """AREA-006（35㎡ 无障碍）普通 room → None"""
        ent = self._entity("room", subtype="", area_m2=40.0)
        assert self._val("AREA-006", ent) is None

    def test_area016_normal_room_returns_none(self):
        """AREA-016（20㎡ 消防控制室）普通 room → None"""
        ent = self._entity("room", subtype="", area_m2=25.0)
        assert self._val("AREA-016", ent) is None

    # ── 守卫 4：target_entities 语义修正 ────────────────────────

    def test_area019_fire_elevator_returns_none(self):
        """AREA-019 消防电梯前室 → fire_elevator 实体是电梯标记而非前室 → None"""
        ent = self._entity("fire_elevator", bbox={"width": 2000, "height": 2000})
        assert self._val("AREA-019", ent) is None

    def test_area013_window_returns_none(self):
        """AREA-013 救援窗净面积 → window 是 CAD 符号 → None"""
        ent = self._entity("window", bbox={"width": 2, "height": 2})
        assert self._val("AREA-013", ent) is None

    def test_area013_rescue_window_returns_none(self):
        """AREA-013 → rescue_window 是文字标注 → None"""
        ent = self._entity("rescue_window", bbox={"width": 397, "height": 265})
        assert self._val("AREA-013", ent) is None

    # ── 守卫 5：bbox 兜底白名单 ──────────────────────────────────

    def test_area_bbox_door_returns_none(self):
        """door 不在白名单 → bbox 兜底被拦截 → None"""
        ent = self._entity("door", bbox={"width": 900, "height": 2100})
        assert self._val("AREA-013", ent) is None

    def test_area_bbox_text_returns_none(self):
        """text 不在白名单 → None"""
        ent = self._entity("text", bbox={"width": 500, "height": 300})
        assert self._val("AREA-013", ent) is None

    # ── 守卫 6：bbox 兜底合理性检查（<0.5㎡ 视为文字框） ────────

    def test_area_bbox_tiny_antechamber_returns_none(self):
        """antechamber bbox 0.18㎡（文字框）→ <0.5 → None"""
        ent = self._entity("antechamber", bbox={"width": 525, "height": 350})
        assert self._val("AREA-018", ent) is None

    def test_area_bbox_small_antechamber_returns_none(self):
        """antechamber bbox 0.4㎡ → <0.5 → None"""
        ent = self._entity("antechamber", bbox={"width": 600, "height": 700})
        assert self._val("AREA-018", ent) is None

    def test_area_bbox_reasonable_antechamber_works(self):
        """antechamber bbox 2.59㎡ → >0.5 → 正常返回"""
        ent = self._entity(
            "antechamber",
            bbox={"width": 1971.52, "height": 1314.35},
        )
        val = self._val("AREA-018", ent)
        assert val is not None
        assert val == pytest.approx(2.59, rel=0.01)

    def test_area_bbox_large_room_works(self):
        """room bbox 100㎡ + 有效 subtype → 正常返回（AREA-004 需 control_room）"""
        ent = self._entity("room", subtype="control_room",
                           bbox={"width": 10000, "height": 10000})
        val = self._val("AREA-004", ent)
        assert val == pytest.approx(100.0)

    def test_area_with_area_m2_bypasses_bbox_check(self):
        """有 area_m2 权威口径时，不受 bbox 合理性检查影响"""
        # 即使 area_m2=0.3 m²（小），也不应被 bbox 守卫拦截
        # 因为 area_m2 是权威数据
        ent = self._entity("room", subtype="control_room", area_m2=0.3)
        val = self._val("AREA-004", ent)
        assert val == pytest.approx(0.3)  # 权威数据直接返回
