"""
BAA 原子函数子包 - 按规范分组
- fire_general.py: GB50016 通用消防 + GB50067 车库消防
- fire_sprinkler.py: GB50974 自动喷水灭火
- fire_alarm.py: GB50116 火灾自动报警
- accessibility.py: GB50763 无障碍
- thermal.py: GB50176 / GB50189 / GB55015 建筑热工设计 + 节能
"""

from .fire_general import MODULE_FUNCS as _fire_general  # 通用消防 + 车库
from .fire_sprinkler import MODULE_FUNCS as _fire_sprinkler  # 自动喷水灭火
from .fire_alarm import MODULE_FUNCS as _fire_alarm  # 火灾自动报警
from .accessibility import MODULE_FUNCS as _accessibility  # 无障碍
from .thermal import MODULE_FUNCS as _thermal  # 建筑热工 + 节能
from .structural import MODULE_FUNCS as _structural  # 结构荷载


def _merge_modules(*modules):
    """合并多个模块的函数列表，按 func_id 去重（后出现的覆盖前出现的）。"""
    registry = {}
    for module in modules:
        for func in module:
            registry[func.func_id] = func
    return list(registry.values())


# 合并所有模块，对外暴露统一的原子函数列表
ATOMIC_FUNCTIONS = _merge_modules(
    _fire_general,
    _fire_sprinkler,
    _fire_alarm,
    _accessibility,
    _thermal,
    _structural,
)

__all__ = ["ATOMIC_FUNCTIONS"]
