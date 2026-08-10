"""
Layer classification rules (modularized).

拆分为 8 个子模块，按语义分组。
"""

from ._layer_rules_core import LAYER_RULES_CORE
from ._layer_rules_fire import LAYER_RULES_FIRE
from ._layer_rules_p70_freq import LAYER_RULES_P70_FREQ
from ._layer_rules_p74 import LAYER_RULES_P74
from ._layer_rules_p70_b5 import LAYER_RULES_P70_B5
from ._layer_rules_p70_tail import LAYER_RULES_P70_TAIL
from ._layer_rules_struct import LAYER_RULES_STRUCT
from ._layer_rules_p79 import LAYER_RULES_P79
from ._layer_rules_short import SHORT_LAYER_RULES


def _merge_dicts(*dicts):
    """Merge dicts; later overrides earlier."""
    result = {}
    for d in dicts:
        result.update(d)
    return result


LAYER_RULES = _merge_dicts(
    LAYER_RULES_CORE,
    LAYER_RULES_FIRE,
    LAYER_RULES_P70_FREQ,
    LAYER_RULES_P74,
    LAYER_RULES_P70_B5,
    LAYER_RULES_P70_TAIL,
    LAYER_RULES_STRUCT,
    LAYER_RULES_P79,
)
