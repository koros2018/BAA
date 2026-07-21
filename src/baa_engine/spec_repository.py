"""BAA 规范 JSON 知识库——薄兼容层。

Clause 数据已从本文件拆出到 `spec_data/` 目录（按标准分片）。
本文件仅为向后兼容保留，内部导入并转发所有公开符号。
"""

# ── 兼容转发 ─────────────────────────────────────────────
# 消费者直接 import 旧路径仍可工作：
#   from src.baa_engine.spec_repository import SpecRepository, Clause, Threshold
#   from src.baa_engine.spec_repository import INITIAL_CLAUSES, GB50974_CLAUSES, ...

from src.baa_engine.spec_data._repo import (  # spec_data loader
    Clause,
    SpecRepository,
    Threshold,
)
from src.baa_engine.spec_data.gb50016_core import INITIAL_CLAUSES  # type: ignore[attr-defined]
from src.baa_engine.spec_data.gb50016_extra import (  # type: ignore[attr-defined]
    GB50016_CLAUSES,
)
from src.baa_engine.spec_data.gb50974 import GB50974_CLAUSES  # type: ignore[attr-defined]
from src.baa_engine.spec_data.gb50763 import GB50763_CLAUSES  # type: ignore[attr-defined]
from src.baa_engine.spec_data.gb50067 import GB50067_CLAUSES  # type: ignore[attr-defined]
from src.baa_engine.spec_data.nfpa import NFPA_CLAUSES  # type: ignore[attr-defined]

__all__ = [
    "Clause",
    "SpecRepository",
    "Threshold",
    "INITIAL_CLAUSES",
    "GB50016_CLAUSES",
    "GB50974_CLAUSES",
    "GB50763_CLAUSES",
    "GB50067_CLAUSES",
    "NFPA_CLAUSES",
]
