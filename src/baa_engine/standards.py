"""T-D1 标准集（StandardSet）抽象层。

设计要点：
- 标准集是一组可同时启用的规范标准 + 可选尺度阈值覆盖。
- 本模块仅做 **数据注册 + 查询解析**，不持有 SpecRepository 实例
  （SpecRepository 仍由 api_globals 模块级全局维护，启动时一次加载所有 clause）。
- 运行时切换：审查任务创建时携带 standard_set_code，
  在执行规范判定前由本模块解析出该集允许的 standard 列表 + 每个原子函数
  对应的 standard，传给 SpecRepository.get_threshold。

关键 API：
    list_sets() -> List[StandardSet]
    load_set(code) -> StandardSet  # 未知 code 抛 KeyError
    StandardSet.resolve_standard(func_id) -> Optional[str]  # 给 get_threshold 用
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── 内置标准集注册表（纯数据，无副作用）────────────────────────

_BUILTIN_SETS: Dict[str, "StandardSet"] = {}


@dataclass
class StandardSet:
    """一套可切换的规范标准集。"""

    code: str  # 唯一标识，如 "CN-National-v1"
    name: str  # 展示名
    version: str  # 语义化版本，如 "v1"
    included_standards: List[str]  # 启用的 standard 字符串（对应 Clause.standard）
    scale_overrides: Dict[str, Dict[str, float]] = field(
        default_factory=dict
    )  # 可选阈值覆盖 {clause_id: {"civil": 1.2, "industrial": 1.5}}
    description: str = ""

    # 内部缓存：func_id -> 首选 standard（从 Clause 表推导）
    _func_to_standard: Dict[str, str] = field(default_factory=dict)

    # ── 注册/查询 ──────────────────────────────────────────
    @staticmethod
    def register(s: "StandardSet") -> "StandardSet":
        _BUILTIN_SETS[s.code] = s
        return s

    @classmethod
    def get(cls, code: str) -> "StandardSet":
        if code not in _BUILTIN_SETS:
            available = ", ".join(sorted(_BUILTIN_SETS.keys())) or "(none)"
            raise KeyError(
                f"未知 standard_set_code='{code}'，可用值：{available}"
            )
        return _BUILTIN_SETS[code]

    @classmethod
    def all(cls) -> List["StandardSet"]:
        return sorted(_BUILTIN_SETS.values(), key=lambda s: s.code)

    # ── 运行时辅助 ──────────────────────────────────────────
    def populate_func_standard_map(self, spec_repo_clauses_iterable) -> None:
        """从 SpecRepository.clauses 中构建 func_id → standard 映射。

        同一个 func_id 可能在 included_standards 多个标准里都有 clause，
        取 first-match（按 included_standards 列表顺序）。
        """
        by_func: Dict[str, List[str]] = {}
        included = set(self.included_standards)
        for clause in spec_repo_clauses_iterable:
            if clause.standard not in included:
                continue
            by_func.setdefault(clause.func_id, []).append(clause.standard)

        first_of = {s: i for i, s in enumerate(self.included_standards)}

        def _pick(func_id: str) -> Optional[str]:
            choices = by_func.get(func_id)
            if not choices:
                return None
            # 取 included_standards 中排名最靠前的
            choices_sorted = sorted(choices, key=lambda s: first_of.get(s, 999))
            return choices_sorted[0]

        self._func_to_standard = {fid: _pick(fid) for fid in by_func}

    def resolve_standard(self, func_id: str) -> Optional[str]:
        """给定原子函数 ID，返回该标准集下应使用的 standard 名称。

        找不到时返回 None，调用方应回退到 SpecRepository 的默认 standard。
        """
        return self._func_to_standard.get(func_id)

    def has_standard(self, standard: str) -> bool:
        return standard in self.included_standards


@dataclass
class ScaleContext:
    """D1-T2：单次审查的尺度上下文。

    把 standard_set_code + StandardSet 实例 + scale_overrides 阈值覆盖
    收拢成一个对象，避免 admin_routes.py 里散落多个临时变量。

    scale_overrides 接口预留：未来 D1-T3 地标导入时，地标对某些 clause
    的阈值覆盖写在这里，优先级高于 SpecRepository 阈值。
    """

    standard_set_code: str
    standard_set: Optional[StandardSet] = None
    # 未来 D1-T3 接口预留：{clause_id: {"civil": 1.3, "industrial": 1.5}}
    scale_overrides: Dict[str, Dict[str, float]] = field(default_factory=dict)

    @classmethod
    def create(cls, code: str) -> "ScaleContext":
        """根据 code 创建；未知 code 时 standard_set=None（admin_routes.py 已做 API 校验）。"""
        try:
            s = load_set(code)
        except KeyError:
            s = None
        return cls(standard_set_code=code, standard_set=s)

    def resolve_standard(self, func_id: str) -> Optional[str]:
        """代理 StandardSet.resolve_standard，None 回退时由调用方兜底。"""
        if self.standard_set is None:
            return None
        return self.standard_set.resolve_standard(func_id)

    def get_override(self, clause_id: str, building_type: str) -> Optional[float]:
        """取 scale_overrides 里的阈值覆盖（优先级高于 SpecRepository）。"""
        bt_map = self.scale_overrides.get(clause_id)
        if not bt_map:
            return None
        return bt_map.get(building_type) or bt_map.get("civil")


# ── 公开 API（函数形式，兼容模块级）─────────────────────────

def list_sets() -> List[StandardSet]:
    return StandardSet.all()


def load_set(code: str) -> StandardSet:
    return StandardSet.get(code)


def available_codes() -> List[str]:
    return sorted(_BUILTIN_SETS.keys())


# ── 内置标准集注册 ──────────────────────────────────────────
#
# CN-National-v1：GB50016（防火）+ GB50974（消防设施）+ GB50763（无障碍）
#                 + GB50067（居住）——当前代码库 4 套国标全覆盖。
#                 注意：NFPA 是海外标准，不含在国内国家级标准集内。
#
# 这里直接硬编码 standard 字符串（与 Clause.standard 字段对齐），
# 不强依赖 spec_data 模块导入——导入副作用留给 SpecRepository 自己。

StandardSet.register(StandardSet(
    code="CN-National-v1",
    name="中国国家级标准（v1）",
    version="v1",
    included_standards=[
        "GB 50016-2014",   # 建筑防火设计规范
        "GB 50016-2018",   # 建筑防火通用规范
        "GB 50974-2014",   # 消防给水及消火栓系统技术规范
        "GB 50763-2012",   # 无障碍设计规范
        "GB 50067-2014",   # 住宅设计规范
    ],
    description="GB 防火 + 消防设施 + 无障碍 + 住宅四件套，当前生产默认集",
))

# NFPA 海外集保留（当前 Clause 里的 NFPA 系列含年份后缀）
StandardSet.register(StandardSet(
    code="US-NFPA-v1",
    name="美国 NFPA 标准（v1）",
    version="v1",
    included_standards=[
        "NFPA 101-2021",
        "NFPA 5000-2021",
        "NFPA 13-2021",
        "NFPA 14-2021",
    ],
    description="NFPA 生命安全 + 建筑规范 + 消防喷淋 + 立管，海外项目使用",
))


# ── 工具函数：SpecRepository 遍历入口 ──────────────────────
#
# 给 StandardSet.populate_func_standard_map 用——需要拿到 Clause 列表。
# SpecRepository 提供了 to_json() / list_all() 等方法，这里再包一层
# 拿到原生 Clause 对象列表，让上层直接调用。

def build_func_standard_maps_for_all_sets(spec_repo_clauses_iterable) -> None:
    """初始化时一次性为所有已注册标准集填充 func→standard 映射。

    建议在引擎预热后调用一次（baa_api.py 里 SpecRepository 实例化之后）。
    """
    for s in StandardSet.all():
        s.populate_func_standard_map(spec_repo_clauses_iterable)
