"""D3-T2 Word 整改通知单 + 复查意见生成器（python-docx）。"""

from .correction_docx import build_correction_notice_docx, build_recheck_opinion_docx

__all__ = ["build_correction_notice_docx", "build_recheck_opinion_docx"]
