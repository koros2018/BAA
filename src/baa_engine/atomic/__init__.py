"""
BAA 原子函数子包 - 按规范分组
- fire_general.py: GB50016 通用消防 + GB50067 车库消防
- fire_sprinkler.py: GB50974 自动喷水灭火
- fire_alarm.py: GB50116 火灾自动报警
- accessibility.py: GB50763 无障碍
- thermal.py: GB50176 / GB50189 / GB55015 建筑热工设计 + 节能
"""

from .fire_general import MODULE_FUNCS as _fire_general  # 通用消防 + 车库
from .fire_sprinkler import MODULE_FUNCS as _fire_sprinkler  # 自动喷水灭火
from .fire_alarm import MODULE_FUNCS as _fire_alarm  # 火灾自动报警
from .accessibility import MODULE_FUNCS as _accessibility  # 无障碍
from .thermal import MODULE_FUNCS as _thermal  # 建筑热工 + 节能
from .structural import MODULE_FUNCS as _structural  # 结构荷载


def _merge_modules(*modules):
    """合并多个模块的函数列表，按 func_id 去重（后出现的覆盖前出现的）。"""
    registry = {}
    for module in modules:
        for func in module:
            registry[func.func_id] = func
    return list(registry.values())


# 合并所有模块，对外暴露统一的原子函数列表
ATOMIC_FUNCTIONS = _merge_modules(
    _fire_general,
    _fire_sprinkler,
    _fire_alarm,
    _accessibility,
    _thermal,
    _structural,
)


# ── P2-1: 2D 图纸不可判定规则（unsupported_2d）───────────────
# 判定依据：规则所需的判据量在二维建筑 DXF 中没有载体。
#   non_geometric      体积(m³)/时间(s)/温度(℃)/人流率(百人)/风速(m/s)
#   product_spec       防火等级/耐火极限/设备参数（图纸不承载产品选型）
#   thermal            传热系数/保温层/遮阳/气密性（需材料热工参数）
#   structural         荷载/配筋率/混凝土强度（需结构计算）
#   illuminance        照度(lx)（需照明设计）
#   mep_data           探测器/消防电气设备数量（需机电专业数据）
#   site_or_path       场地/室外设施定位、无障碍路线
#   semantic_unmapped  2D 无图层/块约定的语义（救援窗、自然排烟口、前室形式）
#   semantic_gap       实体存在但语义不足以判定（需改判据语义）
#   prereq_unsupported 前置规则本身不可判定
#   path_topology      需疏散路径网络/拓扑
# 标记只写元数据，不改变 matches()/execute() 行为，规则照常参与执行与
# 覆盖率分子计算；报告侧用它给出「可判定口径」分母。
UNSUPPORTED_2D_REASONS = {
    # ── C 桶（61）：2D 图纸无载体（原 67 剔除 6 条执行门禁缺陷）──
    "DIM-028": "non_geometric",  # 锅炉房/油室容积 m³
    "DIM-029": "non_geometric",  # 消防电梯迫降时间 s
    "DIM-047": "non_geometric",  # 泵房温度 ℃
    "DIM-057": "non_geometric",  # 舞厅宽度 m/百人（需人数）
    "DIM-061": "non_geometric",  # 消防水池容积 m³
    "DIM-062": "non_geometric",  # 喷淋水池容积 m³
    "DIM-079": "non_geometric",  # 疏散净宽 m/百人
    "DIM-109": "non_geometric",  # 消防水箱容积 m³
    "DIM-111": "non_geometric",  # 排烟风速 m/s
    "DIM-032": "semantic_unmapped",  # 救援窗 1000mm（无救援窗图层约定）
    "DIM-102": "semantic_unmapped",  # 避难区 2.0m（无避难区图层约定）
    "DIM-110": "semantic_unmapped",  # 自然排烟窗面积比 2%（无排烟口图层约定）
    "DIM-114": "semantic_unmapped",  # 消防救援窗 1.0m
    "DIM-115": "semantic_unmapped",  # 前室 1.5m（需前室形式语义）
    "ATTR-004": "product_spec",  # 防火墙耐火极限 3.0h
    "ATTR-005": "product_spec",  # 防火门等级 2.0 级
    "ATTR-006": "product_spec",  # 楼板耐火极限 1.5h
    "ATTR-007": "product_spec",  # 幕墙耐火极限 1.0h
    "ATTR-010": "product_spec",  # 防烟楼梯间前室 4.5㎡
    "ATTR-013": "product_spec",  # 防火窗耐火极限 1.0h
    "ATTR-014": "product_spec",  # 疏散门数量 1.0 处
    "ATTR-016": "product_spec",  # 消防电梯载重 800kg
    "ATTR-017": "product_spec",  # 外墙开口 1.0 处
    "ATTR-018": "product_spec",  # 楼梯踏步 1.0 处
    "ATTR-019": "product_spec",  # 防火门等级 1.0 级
    "ACCESS-012": "semantic_unmapped",  # 盲道与障碍物 0.25m
    "ACCESS-019": "semantic_unmapped",  # 扶手高度 0.85m（竖向量，平面图无）
    "ACCESS-020": "semantic_unmapped",  # 洗手盆深度 0.55m（竖向/设施深度）
    "THERM-001": "thermal",
    "THERM-003": "thermal",
    "THERM-004": "thermal",
    "THERM-006": "thermal",  # 遮阳系数
    "THERM-007": "thermal",
    "THERM-010": "thermal",  # 保温层厚度
    "THERM-012": "thermal",  # 外窗气密性等级
    "THERM-016": "thermal",  # 外窗太阳得热
    "LIGHT-002": "illuminance",
    "LIGHT-003": "illuminance",
    "LIGHT-004": "illuminance",
    "LIGHT-005": "illuminance",
    "LIGHT-007": "illuminance",
    "LIGHT-008": "illuminance",
    "LIGHT-009": "illuminance",
    "LIGHT-010": "illuminance",
    "LIGHT-011": "illuminance",
    "COUNT-004": "non_geometric",  # 油室容积 m³
    "COUNT-027": "mep_data",  # 探测器数量
    "COUNT-028": "mep_data",  # 探测器数量
    "DIST-014": "site_or_path",  # 无障碍厕所 30m
    "DIST-015": "site_or_path",  # 水泵接合器 2m（室外设施）
    "DIST-017": "site_or_path",  # 卧室与水箱 0m
    "DIST-018": "site_or_path",  # 多功能厅与泵房 6m
    "DIST-019": "site_or_path",  # 建筑与储水池 25m
    "DIST-020": "site_or_path",  # 车位与出口 45m
    "STR-001": "structural",
    "STR-002": "structural",
    "STR-003": "structural",
    "STR-006": "structural",  # 柱配筋率
    "STR-007": "structural",  # 柱轴压比
    "STR-014": "structural",  # 混凝土强度
    "AREA-020": "non_geometric",  # 避难区 5 人/m²（需人数）
    # ── 12 条语义缺口（需改判据语义，非补属性可解）──
    "AREA-004": "semantic_gap",
    "AREA-005": "semantic_gap",
    "AREA-006": "semantic_gap",
    "AREA-011": "semantic_gap",
    "AREA-013": "semantic_gap",
    "AREA-016": "semantic_gap",
    "AREA-017": "semantic_gap",
    "AREA-022": "semantic_gap",
    "DIM-005": "semantic_gap",
    "DIM-010": "semantic_gap",
    "DIM-021": "semantic_gap",
    "DIM-022": "semantic_gap",
    # ── 2 条依赖前置不可判定 ──
    "DIM-073": "prereq_unsupported",
    "DIM-075": "prereq_unsupported",
    # ── 3 条需疏散路径拓扑 ──
    "DIST-001": "path_topology",
    # DIM-056/DIM-094（2026-11-16）：疏散距离规则，需疏散路径拓扑而非房间
    # bbox 尺寸。此前 _GENERIC_DIM_RULES 用 room.length/room.width 判定，
    # 产生 1000× 单位错配 + 语义错配的假 FAIL（DIM-056 1470 条、DIM-094
    # 1187 条，全部落在 room 实体）。已从 _GENERIC_DIM_RULES 移除提取分支。
    "DIM-056": "path_topology",
    "DIM-094": "path_topology",
}

# ── P2-1b: 执行门禁缺陷（不计入 unsupported_2d，留在可判定分母）──
# 这 6 条规则的判据本身可从 2D 图纸获得，缺口在实现侧：matches() 因
# subtype/别名组命中而返回 True，进入作用域聚合后 execute(None) 拿到空
# 目标集合，被 targets∩entity_types 硬交集跳过。直接补齐会走
# build_scopes → execute(None)，而这些样本缺 drain/sump/fire_pump 实体，
# 大概率产出假 FAIL，故本轮只登记缺陷、不动执行路径。
IMPLEMENTATION_GATE_DEFECTS = {
    "EXIST-033": "适用面命中但执行侧目标集合为空；缺 drain 实体，直接修会产假 FAIL",
    "EXIST-034": "适用面命中但执行侧目标集合为空；缺备用电源实体",
    "EXIST-035": "适用面命中但执行侧目标集合为空；缺无障碍电梯语义",
    "EXIST-054": "适用面命中但执行侧目标集合为空；疏散门/防火门门禁不一致",
    "EXIST-062": "适用面命中但执行侧目标集合为空；缺 fire_pump 实体",
    "EXIST-095": "适用面命中但执行侧目标集合为空；缺 sump 实体",
}

# ── P133: 实现门禁（能力缺失，不是可判定缺陷）──
# 与 IMPLEMENTATION_GATE_DEFECTS 的区别：后者判据可取、只是执行侧目标集合
# 为空，仍留在可判定分母；本组所需的判据数据在实现侧根本不存在（path_length
# 是 bbox 间隙和而非行走距离），因此剔除出可判定分母，同时保留在全规则口径
# 分母——对外披露的分母不因能力缺失而缩放。
IMPLEMENTATION_GATES = {
    "EVAC-002": "path_length 为最短路径各边 bbox 间隙之和（mm），非行走距离，无法与 30m 阈值比较",
    "EVAC-003": "exceeds_max_distance 由同一 bbox 间隙和与米阈值直接比较得出，非真实超距",
}

for _func in ATOMIC_FUNCTIONS:
    _reason = UNSUPPORTED_2D_REASONS.get(_func.func_id)
    if _reason is not None:
        _func.unsupported_2d = True
        _func.unsupported_reason = _reason
    _defect = IMPLEMENTATION_GATE_DEFECTS.get(_func.func_id)
    if _defect is not None:
        _func.implementation_gate_defect = True
        _func.defect_note = _defect
    _gate = IMPLEMENTATION_GATES.get(_func.func_id)
    if _gate is not None:
        _func.implementation_gate = True
        _func.implementation_gate_reason = _gate

__all__ = [
    "ATOMIC_FUNCTIONS",
    "UNSUPPORTED_2D_REASONS",
    "IMPLEMENTATION_GATE_DEFECTS",
    "IMPLEMENTATION_GATES",
]
