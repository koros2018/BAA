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
        """根据 code 创建；未知 code 时 standard_set=None（admin_routes.py 已做 API 校验）。

        D1-T3：如果 StandardSet 注册了 scale_overrides（地标阈值覆盖），
        深拷贝进 ScaleContext 实例——审查管线里的动态修改不应污染全局注册数据。
        """
        import copy as _copy

        try:
            s = load_set(code)
        except KeyError:
            s = None
        ctx = cls(standard_set_code=code, standard_set=s)
        if s and s.scale_overrides:
            ctx.scale_overrides = _copy.deepcopy(s.scale_overrides)
        return ctx

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


# ── D1-T3：首批地标集（上海 / 广东）─────────────────────────
#
# 设计要点（Roadmap 第 6 节版权风险缓解）：
# 1. 只存 **阈值数字**，不存地标原文条文——避免侵权；
# 2. scale_overrides 的 key 是 **国标 clause_id**（如 GB50016-5.5.18），
#    表示"该国标条款在此地标下的覆盖值"，不引入地标自身条款号体系；
# 3. included_standards 仍为国标列表——地标只做阈值覆盖，不新增 standard；
# 4. 保守原则：仅填公开可查的差异，不确定的不填；
# 5. building_type 目前只覆盖 "civil"（MVP 阶段只有 civil / industrial 两种
#    Query 参数值，未来加 commercial 后可扩）。

# 上海地标（DGJ08-20 住宅设计标准 + DG/TJ 08-2408 城市综合体消防技术标准
#         + 人员密集场所疏散通道要点）
StandardSet.register(StandardSet(
    code="CN-Shanghai-v1",
    name="中国 上海地方标准（v1）",
    version="v1",
    included_standards=[
        "GB 50016-2014",
        "GB 50016-2018",
        "GB 50974-2014",
        "GB 50763-2012",
        "GB 50067-2014",
    ],
    scale_overrides={
        # GB50016-5.5.18-2 疏散走道净宽：国标 civil=1.1m → 上海住宅走廊 ≥1.2m
        # （来源：DGJ08-20-2018 住宅设计标准 5.3.1 条）
        "GB50016-5.5.18-2": {"civil": 1.2},
        # GB50016-7.1.1 消防车道宽度：国标 civil=4.0m → 上海综合体 ≥4.5m
        # （来源：DG/TJ 08-2408-2022 城市综合体消防 3.2 加严要求）
        "GB50016-7.1.1": {"civil": 4.5},
        # GB50016-5.5.18 疏散楼梯净宽：国标 civil=1.2m → 上海大型建筑 ≥1.3m
        # （来源：上海人员密集场所疏散通道技术要点 1.2.1 表，一/二级耐火
        #  每百人 0.65m 推算 + 最小净宽加严）
        "GB50016-5.5.18": {"civil": 1.3},
    },
    description="上海地标阈值覆盖：住宅走道+综合体消防车道+大型建筑楼梯净宽",
))

# 广东地标（DBJ15-31 建筑防火设计规程 + 广东省公安厅大中型商业建筑意见）
StandardSet.register(StandardSet(
    code="CN-Guangdong-v1",
    name="中国 广东地方标准（v1）",
    version="v1",
    included_standards=[
        "GB 50016-2014",
        "GB 50016-2018",
        "GB 50974-2014",
        "GB 50763-2012",
        "GB 50067-2014",
    ],
    scale_overrides={
        # GB50016-5.5.18-2 疏散走道净宽：国标 civil=1.1m → 广东商业主通道 ≥3.0m
        # （来源：广东省公安厅 2014 大中型商业建筑意见 第 1 条第 2 款）
        # 注意：此值针对大中型商业建筑，非全建筑类型——MVP 阶段
        # building_type 无 commercial 选项，暂用 civil 表示地标整体加严
        "GB50016-5.5.18-2": {"civil": 3.0},
        # GB50016-5.5.17 房间疏散距离：国标 civil=30m → 广东商业 ≤25m
        # （来源：广东商业建筑消防设计审查要点，商业疏散距离比国标严 5m）
        "GB50016-5.5.17": {"civil": 25.0},
        # GB50016-5.5.18-3 疏散门净宽：国标 civil=0.9m → 广东 ≥1.0m
        # （来源：DBJ15-31 系列地标消防设施配置加严）
        "GB50016-5.5.18-3": {"civil": 1.0},
    },
    description="广东地标阈值覆盖：商业主通道+疏散距离+疏散门净宽",
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
