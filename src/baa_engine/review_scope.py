"""图幅适用范围门控（P121 后续 · A 类止血）。

部分原子函数以「房间-门-出口」平面拓扑为判定前提（EVAC-002 疏散距离、
EVAC-003 路径合规、EVAC-004 瓶颈净宽）。在非平面图幅
（``scope_mode != "plan"``）上，房间与门都是从立面/大样构件里拼出来的，
判据前提不成立。执行前剔除这些函数：既不产生 finding，也不计入
applicable 分母，并在输出中标记 ``not_applicable``，避免把「不适用」
混同为「通过」或「违规」。

缺省/非法 ``scope_mode`` 按 ``plan`` 处理，保持历史调用方
（无 ``sheet_type`` 的测试桩与旧接口）行为不变。
"""

from __future__ import annotations

from typing import Any, Iterable, List, Sequence

# 仅平面图适用：依赖房间-门-出口拓扑
PLAN_ONLY_FUNC_IDS: tuple = ("EVAC-002", "EVAC-003", "EVAC-004")
PLAN_ONLY_REASON = "依赖平面疏散拓扑（房间-门-出口），非平面图幅不适用"

_VALID_SCOPE_MODES = ("plan", "non_plan", "unknown")


def normalize_scope_mode(scope_mode: Any) -> str:
    """归一化图幅作用域；缺省/非法值按 plan（保持旧行为）。"""
    if scope_mode in _VALID_SCOPE_MODES:
        return str(scope_mode)
    return "plan"


def is_plan_scope(scope_mode: Any) -> bool:
    return normalize_scope_mode(scope_mode) == "plan"


def filter_plan_only_func_ids(func_ids: Iterable[str], scope_mode: Any) -> List[str]:
    """非平面图幅时剔除仅平面适用的函数 ID，保留原顺序。"""
    ids = list(func_ids)
    if is_plan_scope(scope_mode):
        return ids
    return [fid for fid in ids if fid not in PLAN_ONLY_FUNC_IDS]


def filter_plan_only_funcs(funcs: Sequence[Any], scope_mode: Any) -> List[Any]:
    """非平面图幅时剔除仅平面适用的函数对象，保留原顺序。"""
    items = list(funcs)
    if is_plan_scope(scope_mode):
        return items
    return [f for f in items if getattr(f, "func_id", "") not in PLAN_ONLY_FUNC_IDS]


def not_applicable_func_ids(scope_mode: Any) -> List[str]:
    """当前图幅下被标记为不适用的函数 ID（升序）。"""
    if is_plan_scope(scope_mode):
        return []
    return sorted(PLAN_ONLY_FUNC_IDS)
