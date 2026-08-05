"""BAA 规范条款数据——按标准分片加载。

使用方式：
    from src.baa_engine.spec_data import (
        INITIAL_CLAUSES, GB50016_CLAUSES, GB50974_CLAUSES,
        GB50763_CLAUSES, GB50067_CLAUSES, NFPA_CLAUSES,
    )
    # 或直接 import 单个文件：
    # from src.baa_engine.spec_data.gb50016_core import INITIAL_CLAUSES
"""

from .gb50016_core import INITIAL_CLAUSES
from .gb50016_extra import GB50016_CLAUSES
from .gb50974 import GB50974_CLAUSES
from .gb50763 import GB50763_CLAUSES
from .gb50067 import GB50067_CLAUSES
from .nfpa import NFPA_CLAUSES
from .construction_review import get_construction_review_items

__all__ = [
    "INITIAL_CLAUSES",
    "GB50016_CLAUSES",
    "GB50974_CLAUSES",
    "GB50763_CLAUSES",
    "GB50067_CLAUSES",
    "NFPA_CLAUSES",
    "get_construction_review_items",
]
