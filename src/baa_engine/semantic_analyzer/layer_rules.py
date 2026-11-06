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


def is_substring_keyword(keyword: str) -> bool:
    """长表子串匹配的合法关键字。

    ASCII 关键字（"C"、"SB"、"0" 等 1–2 字符）太短，子串匹配会命中任意
    含该字符的层名（如 "C" 命中 "01 - DWGFREE.com"），必须走短表全词匹配。
    中文关键字按语义天然是子串匹配（如 "楼梯间"），不受长度限制。
    """
    return len(keyword) >= 3 or not keyword.isascii()


_merged = _merge_dicts(
    LAYER_RULES_CORE,
    LAYER_RULES_FIRE,
    LAYER_RULES_P70_FREQ,
    LAYER_RULES_P74,
    LAYER_RULES_P70_B5,
    LAYER_RULES_P70_TAIL,
    LAYER_RULES_STRUCT,
    LAYER_RULES_P79,
)

# T5: 从长表剔除 1–2 字符 ASCII 关键字（已迁入 SHORT_LAYER_RULES 全词匹配），
# 避免子串匹配把任意含该字母的层名整体误判。
LAYER_RULES = {
    k: v for k, v in _merged.items() if is_substring_keyword(k)
}
