"""
BAA 原子函数 - Fire General (模块化)
拆分自 fire_general.py，按类别分为 8 个子模块
"""

from .dim_functions import MODULE_FUNCS as _dim_functions  # DIM
from .distance_functions import MODULE_FUNCS as _distance_functions  # DIST
from .exist_functions import MODULE_FUNCS as _exist_functions  # EXIST
from .area_functions import MODULE_FUNCS as _area_functions  # AREA
from .count_functions import MODULE_FUNCS as _count_functions  # COUNT
from .attr_functions import MODULE_FUNCS as _attr_functions  # ATTR
from .light_functions import MODULE_FUNCS as _light_functions  # LIGHT
from .evac_functions import MODULE_FUNCS as _evac_functions  # EVAC

MODULE_FUNCS = (
    _dim_functions
    + _distance_functions
    + _exist_functions
    + _area_functions
    + _count_functions
    + _attr_functions
    + _light_functions
    + _evac_functions
)
