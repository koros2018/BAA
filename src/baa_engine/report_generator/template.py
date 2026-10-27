"""D3-T1 交付物包模板系统：2 套内置模板 + 企业自定义 JSON 配置。

模板定义封面/报告标题/配色/章节顺序等元数据；ReviewReport 渲染时根据 template_code
选择配色与章节编排。企业可通过 JSON 配置文件上传自定义模板。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 内置模板 ────────────────────────────────────────────────

@dataclass
class ReportTemplate:
    code: str
    name: str
    description: str
    primary_color: str = "#1a365d"
    accent_color: str = "#2b6cb0"
    title: str = "审查报告"
    sections: List[str] = field(default_factory=lambda: ["cover", "summary", "violations", "score"])
    footer_text: str = "BAA 智能审查平台"
    logo_path: Optional[str] = None


BUILTIN_TEMPLATES: Dict[str, ReportTemplate] = {
    "national": ReportTemplate(
        code="national",
        name="国标审查模板",
        description="依据国家标准 GB/T 系列的审查报告模板",
        primary_color="#1a365d",
        accent_color="#2b6cb0",
        title="国家标准审查报告",
        sections=["cover", "score", "summary", "violations", "corrections", "toc", "conclusion", "signature"],
        footer_text="依据 GB/T 系列国家标准",
    ),
    "local": ReportTemplate(
        code="local",
        name="地标审查模板",
        description="依据地方标准（上海/北京/深圳等）的审查报告模板",
        primary_color="#744210",
        accent_color="#b7791f",
        title="地方标准审查报告",
        sections=["cover", "score", "summary", "violations", "corrections", "toc", "conclusion", "signature"],
        footer_text="依据地方标准",
    ),
}


class TemplateRegistry:
    """模板注册表：内置 + 企业自定义。"""

    def __init__(self):
        self._templates: Dict[str, ReportTemplate] = dict(BUILTIN_TEMPLATES)
        self._custom_dir: Optional[Path] = None

    def register(self, tpl: ReportTemplate) -> None:
        self._templates[tpl.code] = tpl
        logger.info(f"[D3-T1] Registered template: {tpl.code}")

    def get(self, code: str) -> ReportTemplate:
        if code in self._templates:
            return self._templates[code]
        logger.warning(f"[D3-T1] Unknown template {code}, fallback to national")
        return self._templates["national"]

    def all(self) -> List[ReportTemplate]:
        return list(self._templates.values())

    def load_custom_from_dir(self, directory: str) -> int:
        """从目录加载企业自定义 JSON 模板，返回加载数量。"""
        d = Path(directory)
        if not d.is_dir():
            return 0
        count = 0
        for f in d.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                tpl = ReportTemplate(**data)
                self.register(tpl)
                count += 1
            except Exception as e:
                logger.warning(f"[D3-T1] Failed to load template {f}: {e}")
        return count


# ── 单例 ────────────────────────────────────────────────────

_registry: Optional[TemplateRegistry] = None


def get_template_registry() -> TemplateRegistry:
    global _registry
    if _registry is None:
        _registry = TemplateRegistry()
        # 尝试加载企业自定义模板目录
        custom_dir = Path("src/data/templates")
        if custom_dir.is_dir():
            _registry.load_custom_from_dir(str(custom_dir))
    return _registry


def reset_template_registry_for_test() -> None:
    global _registry
    _registry = None
