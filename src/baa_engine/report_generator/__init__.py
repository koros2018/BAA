"""BAA 审查报告 PDF 生成器（重构包）"""

from .main import ReviewReport
from .components import ensure_font, build_styles, make_table, _FONT_REGISTERED

__all__ = ["ReviewReport", "ensure_font", "build_styles", "make_table"]
