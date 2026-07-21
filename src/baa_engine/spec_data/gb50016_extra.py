"""
BAA 规范JSON知识库
10 条 L1 + 10 条 L2 级规范（GB50016-2014 / GB50016-2018 建筑防火规范）
支持 building_type 维度阈值（民用/工业）
"""

from typing import Dict, List, Optional, Tuple  # typing: type hints
from dataclasses import dataclass, field  # dataclass support
import json  # stdlib: JSON


@dataclass  # code
class Threshold:  # class definition
    """规范阈值，支持按建筑类型区分"""

    value: float  # 操作
    unit: str  # 操作
    operator: str  # >=, <=, ==, !=
    building_types: Optional[Dict[str, float]] = None  # {"civil": 值, "industrial": 值}


@dataclass  # code
class Clause:  # class definition
    """规范条款"""

    clause_id: str  # 操作
    standard: str  # 操作
    title: str  # 操作
    text: str  # 操作
    level: str  # L1 / L2 / L3
    func_id: str  # 对应原子函数 ID
    category: str  # fire_safety / evacuation / structure / lighting / hvac
    params: Dict = field(default_factory=dict)  # function call
    threshold: Optional[Threshold] = None  # 可选：带建筑类型区分的阈值


GB50016_CLAUSES = [
    # 自动生成的规范条款（匹配现有原子函数）
    # GB50016-8.2.2: 消防水泵判定
    Clause(
        clause_id="GB50016-8.2.2",
        standard="GB 50016-2014",
        title="消防水泵判定",
        text="一类高层应设消防水泵",
        level="L1",
        func_id="EXIST-013",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="有/无", operator="==", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-8.5.3: 排烟设备判定
    Clause(
        clause_id="GB50016-8.5.3",
        standard="GB 50016-2014",
        title="排烟设备判定",
        text="一类高层应设排烟设备",
        level="L1",
        func_id="EXIST-015",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="有/无", operator="==", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-10.3.2: 楼梯间应急照明照度判定
    Clause(
        clause_id="GB50016-10.3.2",
        standard="GB 50016-2014",
        title="楼梯间应急照明照度判定",
        text="楼梯间、前室等疏散照明照度不应低于5.0lx",
        level="L1",
        func_id="LIGHT-002",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=5.0, unit="lx", operator=">=", building_types={"civil": 5.0, "industrial": 5.0}
        ),
    ),
    # GB50016-7.1.8: 消防车道净高判定
    Clause(
        clause_id="GB50016-7.1.8",
        standard="GB 50016-2014",
        title="消防车道净高判定",
        text="消防车道净高不应小于4.0m",
        level="L1",
        func_id="DIM-011",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=4.0, unit="m", operator=">=", building_types={"civil": 4.0, "industrial": 4.0}
        ),
    ),
    # GB50016-6.4.14: 避难走道净宽判定
    Clause(
        clause_id="GB50016-6.4.14",
        standard="GB 50016-2014",
        title="避难走道净宽判定",
        text="避难走道净宽不应小于任一防火分区疏散总净宽",
        level="L1",
        func_id="DIM-012",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="m", operator=">=", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-7.2.5: 救援窗口间距判定
    Clause(
        clause_id="GB50016-7.2.5",
        standard="GB 50016-2014",
        title="救援窗口间距判定",
        text="消防救援窗口间距不应大于20m",
        level="L1",
        func_id="DIST-004",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=20.0, unit="m", operator="<=", building_types={"civil": 20.0, "industrial": 20.0}
        ),
    ),
    # GB50016-5.3.1: 防火分区最大允许建筑面积判定
    Clause(
        clause_id="GB50016-5.3.1",
        standard="GB 50016-2014",
        title="防火分区最大允许建筑面积判定",
        text="一、二级耐火等级建筑防火分区最大允许建筑面积（GB50016-5.3.1）",
        level="L1",
        func_id="DIM-017",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2500.0,
            unit="sqm",
            operator="le",
            building_types={"civil": 2500.0, "industrial": 2500.0},
        ),
    ),
    # GB50016-6.4.3: 防烟楼梯间前室面积判定
    Clause(
        clause_id="GB50016-6.4.3",
        standard="GB 50016-2014",
        title="防烟楼梯间前室面积判定",
        text="防烟楼梯间前室使用面积不应小于6.0sqm（GB50016-6.4.3）",
        level="L1",
        func_id="DIM-018",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=6.0, unit="sqm", operator="ge", building_types={"civil": 6.0, "industrial": 6.0}
        ),
    ),
    # GB50016-5.5.2: 两个安全出口间距判定
    Clause(
        clause_id="GB50016-5.5.2",
        standard="GB 50016-2014",
        title="两个安全出口间距判定",
        text="两个安全出口之间的间距不应小于5.0m（GB50016-5.5.2）",
        level="L1",
        func_id="DIST-005",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=5000.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 5000.0, "industrial": 5000.0},
        ),
    ),
    # GB50016-9.2.3: 排烟口与安全出口间距判定
    Clause(
        clause_id="GB50016-9.2.3",
        standard="GB 50016-2014",
        title="排烟口与安全出口间距判定",
        text="排烟口与安全出口之间的距离不应小于1.5m（GB50016-9.2.3）",
        level="L1",
        func_id="DIST-006",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1500.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 1500.0, "industrial": 1500.0},
        ),
    ),
    # GB50016-5.5.23: 高层建筑避难层数量判定
    Clause(
        clause_id="GB50016-5.5.23",
        standard="GB 50016-2014",
        title="高层建筑避难层数量判定",
        text="建筑高度大于100m时每50m应设一个避难层（GB50016-5.5.23）",
        level="L1",
        func_id="COUNT-002",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-10.3.3: 消防控制室应急照明照度判定
    Clause(
        clause_id="GB50016-10.3.3",
        standard="GB 50016-2014",
        title="消防控制室应急照明照度判定",
        text="消防控制室、消防水泵房等应保持正常照明照度（GB50016-10.3.3）",
        level="L1",
        func_id="LIGHT-003",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=100.0,
            unit="lx",
            operator="ge",
            building_types={"civil": 100.0, "industrial": 100.0},
        ),
    ),
    # GB50016-5.5.16: 观众厅疏散门数量判定
    Clause(
        clause_id="GB50016-5.5.16",
        standard="GB 50016-2014",
        title="观众厅疏散门数量判定",
        text="观众厅每个疏散门的平均疏散人数不应超过250人（GB50016-5.5.16）",
        level="L1",
        func_id="DIM-024",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.0, unit="个", operator="ge", building_types={"civil": 2.0, "industrial": 2.0}
        ),
    ),
    # GB50016-5.5.20: 地下建筑疏散楼梯宽度判定
    Clause(
        clause_id="GB50016-5.5.20",
        standard="GB 50016-2014",
        title="地下建筑疏散楼梯宽度判定",
        text="地下或半地下建筑疏散楼梯净宽度不应小于1.1m（GB50016-5.5.20）",
        level="L1",
        func_id="DIM-025",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1100.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 1100.0, "industrial": 1100.0},
        ),
    ),
    # GB50016-6.4.5: 室外疏散楼梯净宽判定
    Clause(
        clause_id="GB50016-6.4.5",
        standard="GB 50016-2014",
        title="室外疏散楼梯净宽判定",
        text="室外疏散楼梯净宽度不应小于0.9m（GB50016-6.4.5）",
        level="L1",
        func_id="DIM-026",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=900.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 900.0, "industrial": 900.0},
        ),
    ),
    # GB50016-8.3.3: 自动喷水灭火系统判定
    Clause(
        clause_id="GB50016-8.3.3",
        standard="GB 50016-2014",
        title="自动喷水灭火系统判定",
        text="一类高层民用建筑应设自动喷水灭火系统（GB50016-8.3.3）",
        level="L1",
        func_id="EXIST-018",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-8.6.1: 消防专用电话判定
    Clause(
        clause_id="GB50016-8.6.1",
        standard="GB 50016-2014",
        title="消防专用电话判定",
        text="消防控制室应设消防专用电话总机（GB50016-8.6.1）",
        level="L1",
        func_id="EXIST-019",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-8.1.6: 消防控制室判定
    Clause(
        clause_id="GB50016-8.1.6",
        standard="GB 50016-2014",
        title="消防控制室判定",
        text="设有火灾自动报警系统的建筑应设消防控制室（GB50016-8.1.6）",
        level="L1",
        func_id="EXIST-020",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-9.3.1: 机械排烟系统排烟量判定
    Clause(
        clause_id="GB50016-9.3.1",
        standard="GB 50016-2014",
        title="机械排烟系统排烟量判定",
        text="机械排烟系统最小排烟量不应小于7200m³/h（GB50016-9.3.1）",
        level="L1",
        func_id="DIM-027",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=7200.0,
            unit="m3h",
            operator="ge",
            building_types={"civil": 7200.0, "industrial": 7200.0},
        ),
    ),
    # GB50016-5.4.15: 储油间储油量判定
    Clause(
        clause_id="GB50016-5.4.15",
        standard="GB 50016-2014",
        title="储油间储油量判定",
        text="锅炉房储油间储油量不应大于1m³（GB50016-5.4.15）",
        level="L1",
        func_id="DIM-028",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="m3", operator="le", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-7.3.8: 消防电梯运行速度判定
    Clause(
        clause_id="GB50016-7.3.8",
        standard="GB 50016-2014",
        title="消防电梯运行速度判定",
        text="消防电梯从首层到顶层运行时间不应超过60s（GB50016-7.3.8）",
        level="L1",
        func_id="DIM-029",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=60.0, unit="s", operator="le", building_types={"civil": 60.0, "industrial": 60.0}
        ),
    ),
    # GB50016-8.1.7: 消防控制室面积判定
    Clause(
        clause_id="GB50016-8.1.7",
        standard="GB 50016-2014",
        title="消防控制室面积判定",
        text="消防控制室面积不应小于30sqm（GB50016-8.1.7）",
        level="L1",
        func_id="AREA-004",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30.0,
            unit="sqm",
            operator="ge",
            building_types={"civil": 30.0, "industrial": 30.0},
        ),
    ),
    # GB50016-7.2.2: 消防救援场地宽度判定
    Clause(
        clause_id="GB50016-7.2.2",
        standard="GB 50016-2014",
        title="消防救援场地宽度判定",
        text="消防救援场地宽度不应小于10m（GB50016-7.2.2）",
        level="L1",
        func_id="DIM-030",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=10000.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 10000.0, "industrial": 10000.0},
        ),
    ),
    # GB50016-7.1.3: 消防车道转弯半径判定
    Clause(
        clause_id="GB50016-7.1.3",
        standard="GB 50016-2014",
        title="消防车道转弯半径判定",
        text="消防车道转弯半径不应小于9m（GB50016-7.1.3）",
        level="L1",
        func_id="DIM-031",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=9000.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 9000.0, "industrial": 9000.0},
        ),
    ),
    # GB50016-5.5.25: 封闭楼梯间数量判定
    Clause(
        clause_id="GB50016-5.5.25",
        standard="GB 50016-2014",
        title="封闭楼梯间数量判定",
        text="建筑高度不大于21m的住宅建筑可采用敞开楼梯间（GB50016-5.5.25）",
        level="L1",
        func_id="COUNT-003",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-6.4.11: 疏散门开启方向判定
    Clause(
        clause_id="GB50016-6.4.11",
        standard="GB 50016-2014",
        title="疏散门开启方向判定",
        text="疏散门应向疏散方向开启（GB50016-6.4.11）",
        level="L1",
        func_id="EXIST-021",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-6.3.5: 防火阀设置判定
    Clause(
        clause_id="GB50016-6.3.5",
        standard="GB 50016-2014",
        title="防火阀设置判定",
        text="通风管道穿越防火分区处应设防火阀（GB50016-6.3.5）",
        level="L1",
        func_id="EXIST-022",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-10.2.1: 电气线路防火保护判定
    Clause(
        clause_id="GB50016-10.2.1",
        standard="GB 50016-2014",
        title="电气线路防火保护判定",
        text="消防配电线路应采用阻燃电缆并采取防火保护措施（GB50016-10.2.1）",
        level="L1",
        func_id="EXIST-024",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-5.1.2: 楼板耐火极限判定
    Clause(
        clause_id="GB50016-5.1.2",
        standard="GB 50016-2014",
        title="楼板耐火极限判定",
        text="一级耐火等级建筑楼板耐火极限不应低于1.50h（GB50016-5.1.2）",
        level="L1",
        func_id="ATTR-006",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.5, unit="h", operator="ge", building_types={"civil": 1.5, "industrial": 1.5}
        ),
    ),
    # GB50016-6.2.9: 建筑幕墙防火判定
    Clause(
        clause_id="GB50016-6.2.9",
        standard="GB 50016-2014",
        title="建筑幕墙防火判定",
        text="建筑幕墙在每层楼板处应采用防火封堵（GB50016-6.2.9）",
        level="L1",
        func_id="ATTR-007",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="h", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-5.5.17: 地下商店疏散距离判定
    Clause(
        clause_id="GB50016-5.5.17-3",
        standard="GB 50016-2014",
        title="地下商店疏散距离判定",
        text="地下商店疏散距离不应大于30m（GB50016-5.5.17-3）",
        level="L1",
        func_id="DIM-056",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30.0, unit="m", operator="le", building_types={"civil": 30.0, "industrial": 30.0}
        ),
    ),
    # GB50016-5.5.21: 歌舞娱乐放映场所疏散宽度判定
    Clause(
        clause_id="GB50016-5.5.21-2",
        standard="GB 50016-2014",
        title="歌舞娱乐放映场所疏散宽度判定",
        text="歌舞娱乐放映场所疏散总净宽不应小于每100人1.0m（GB50016-5.5.21-2）",
        level="L1",
        func_id="DIM-057",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0,
            unit="m/百人",
            operator="ge",
            building_types={"civil": 1.0, "industrial": 1.0},
        ),
    ),
    # GB50016-5.5.24: 高层病房楼避难间面积判定
    Clause(
        clause_id="GB50016-5.5.24-2",
        standard="GB 50016-2014",
        title="高层病房楼避难间面积判定",
        text="高层病房楼避难间净面积不应小于25.0sqm（GB50016-5.5.24-2）",
        level="L1",
        func_id="DIM-058",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=25.0,
            unit="sqm",
            operator="ge",
            building_types={"civil": 25.0, "industrial": 25.0},
        ),
    ),
    # GB50016-5.5.24: 手术室避难间面积判定
    Clause(
        clause_id="GB50016-5.5.24-3",
        standard="GB 50016-2014",
        title="手术室避难间面积判定",
        text="手术室避难间净面积不应小于25.0sqm（GB50016-5.5.24-3）",
        level="L1",
        func_id="AREA-007",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=25.0,
            unit="sqm",
            operator="ge",
            building_types={"civil": 25.0, "industrial": 25.0},
        ),
    ),
    # GB50016-7.3.2: 消防电梯数量判定
    Clause(
        clause_id="GB50016-7.3.2",
        standard="GB 50016-2014",
        title="消防电梯数量判定",
        text="高层民用建筑每个防火分区消防电梯不应少于1台（GB50016-7.3.2）",
        level="L1",
        func_id="COUNT-014",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="台", operator="ge", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-10.1.6: 应急电源设置判定
    Clause(
        clause_id="GB50016-10.1.6",
        standard="GB 50016-2014",
        title="应急电源设置判定",
        text="消防控制室、消防水泵房等应设应急电源（GB50016-10.1.6）",
        level="L1",
        func_id="EXIST-042",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="台", operator="ge", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-8.3.8: 气体灭火系统判定
    Clause(
        clause_id="GB50016-8.3.8",
        standard="GB 50016-2014",
        title="气体灭火系统判定",
        text="变配电室、计算机房等应设气体灭火系统（GB50016-8.3.8）",
        level="L1",
        func_id="EXIST-043",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="套", operator="ge", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-10.2.3: 配电箱防火判定
    Clause(
        clause_id="GB50016-10.2.3",
        standard="GB 50016-2014",
        title="配电箱防火判定",
        text="配电箱不应直接安装在可燃材料上（GB50016-10.2.3）",
        level="L1",
        func_id="EXIST-045",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="台", operator="ge", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-5.5.13: 走道最小净宽度判定
    Clause(
        clause_id="GB50016-5.5.13",
        standard="GB 50016-2014",
        title="走道最小净宽度判定",
        text="疏散走道最小净宽度不应小于1.1m（GB50016-5.5.13）",
        level="L1",
        func_id="DIM-078",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.1, unit="m", operator=">=", building_types={"civil": 1.1, "industrial": 1.1}
        ),
    ),
    # GB50016-5.5.15: 房间疏散门数量判定
    Clause(
        clause_id="GB50016-5.5.15",
        standard="GB 50016-2014",
        title="房间疏散门数量判定",
        text="公共建筑内每个房间疏散门不应少于2个（GB50016-5.5.15）",
        level="L1",
        func_id="COUNT-016",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.0, unit="个", operator=">=", building_types={"civil": 2.0, "industrial": 2.0}
        ),
    ),
    # GB50016-5.5.21: 疏散宽度指标判定
    Clause(
        clause_id="GB50016-5.5.21",
        standard="GB 50016-2014",
        title="疏散宽度指标判定",
        text="人员密集场所疏散宽度应按百人宽度指标计算（GB50016-5.5.21）",
        level="L1",
        func_id="DIM-079",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0,
            unit="m/百人",
            operator=">=",
            building_types={"civil": 1.0, "industrial": 1.0},
        ),
    ),
    # GB50016-5.5.26: 住宅剪刀楼梯判定
    Clause(
        clause_id="GB50016-5.5.26",
        standard="GB 50016-2014",
        title="住宅剪刀楼梯判定",
        text="住宅建筑剪刀楼梯间应设前室（GB50016-5.5.26）",
        level="L1",
        func_id="EXIST-050",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-5.5.29: 住宅安全出口数量判定
    Clause(
        clause_id="GB50016-5.5.29",
        standard="GB 50016-2014",
        title="住宅安全出口数量判定",
        text="住宅建筑每个单元安全出口不应少于2个（GB50016-5.5.29）",
        level="L1",
        func_id="COUNT-017",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.0, unit="个", operator=">=", building_types={"civil": 2.0, "industrial": 2.0}
        ),
    ),
    # GB50016-5.5.30: 住宅走道宽度判定
    Clause(
        clause_id="GB50016-5.5.30",
        standard="GB 50016-2014",
        title="住宅走道宽度判定",
        text="住宅建筑疏散走道净宽度不应小于1.1m（GB50016-5.5.30）",
        level="L1",
        func_id="DIM-080",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.1, unit="m", operator=">=", building_types={"civil": 1.1, "industrial": 1.1}
        ),
    ),
    # GB50016-5.5.31: 住宅楼梯间形式判定
    Clause(
        clause_id="GB50016-5.5.31",
        standard="GB 50016-2014",
        title="住宅楼梯间形式判定",
        text="住宅建筑高度大于54m时每单元应设1个防烟楼梯间（GB50016-5.5.31）",
        level="L1",
        func_id="EXIST-051",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-6.1.5: 防火墙上不应开设门窗洞口判定
    Clause(
        clause_id="GB50016-6.1.5",
        standard="GB 50016-2014",
        title="防火墙上不应开设门窗洞口判定",
        text="防火墙上不应开设门、窗、洞口（GB50016-6.1.5）",
        level="L1",
        func_id="EXIST-052",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="not_exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-6.2.5: 管道井防火封堵判定
    Clause(
        clause_id="GB50016-6.2.5",
        standard="GB 50016-2014",
        title="管道井防火封堵判定",
        text="管道井应在每层楼板处进行防火封堵（GB50016-6.2.5）",
        level="L1",
        func_id="EXIST-053",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-6.4.2: 封闭楼梯间门宽度判定
    Clause(
        clause_id="GB50016-6.4.2",
        standard="GB 50016-2014",
        title="封闭楼梯间门宽度判定",
        text="封闭楼梯间门应向疏散方向开启，净宽不小于1.0m（GB50016-6.4.2）",
        level="L1",
        func_id="DIM-082",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="m", operator=">=", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-6.4.6: 室外楼梯净宽判定
    Clause(
        clause_id="GB50016-6.4.6",
        standard="GB 50016-2014",
        title="室外楼梯净宽判定",
        text="室外疏散楼梯净宽度不应小于0.9m（GB50016-6.4.6）",
        level="L1",
        func_id="DIM-083",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.9, unit="m", operator=">=", building_types={"civil": 0.9, "industrial": 0.9}
        ),
    ),
    # GB50016-6.4.7: 首层疏散门净宽判定
    Clause(
        clause_id="GB50016-6.4.7",
        standard="GB 50016-2014",
        title="首层疏散门净宽判定",
        text="首层疏散外门净宽度不应小于1.2m（GB50016-6.4.7）",
        level="L1",
        func_id="DIM-084",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.2, unit="m", operator=">=", building_types={"civil": 1.2, "industrial": 1.2}
        ),
    ),
    # GB50016-6.7.4: 保温材料燃烧性能判定
    Clause(
        clause_id="GB50016-6.7.4",
        standard="GB 50016-2014",
        title="保温材料燃烧性能判定",
        text="建筑外墙保温材料燃烧性能不应低于B1级（GB50016-6.7.4）",
        level="L1",
        func_id="ATTR-011",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="级", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-7.1.2: 消防车道净高判定
    Clause(
        clause_id="GB50016-7.1.2",
        standard="GB 50016-2014",
        title="消防车道净高判定",
        text="消防车道净高不应小于4.0m（GB50016-7.1.2）",
        level="L1",
        func_id="DIM-085",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=4.0, unit="m", operator=">=", building_types={"civil": 4.0, "industrial": 4.0}
        ),
    ),
    # GB50016-7.1.4: 消防车道转弯半径判定
    Clause(
        clause_id="GB50016-7.1.4",
        standard="GB 50016-2014",
        title="消防车道转弯半径判定",
        text="消防车道转弯半径不应小于12m（GB50016-7.1.4）",
        level="L1",
        func_id="DIM-086",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=12.0, unit="m", operator=">=", building_types={"civil": 12.0, "industrial": 12.0}
        ),
    ),
    # GB50016-7.2.1: 消防救援场地面积判定
    Clause(
        clause_id="GB50016-7.2.1",
        standard="GB 50016-2014",
        title="消防救援场地面积判定",
        text="消防救援场地长度不应小于15m，宽度不应小于10m（GB50016-7.2.1）",
        level="L1",
        func_id="AREA-010",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=150.0,
            unit="㎡",
            operator=">=",
            building_types={"civil": 150.0, "industrial": 150.0},
        ),
    ),
    # GB50016-7.2.3: 救援窗口尺寸判定
    Clause(
        clause_id="GB50016-7.2.3",
        standard="GB 50016-2014",
        title="救援窗口尺寸判定",
        text="救援窗口净高不应小于1.0m，净宽不应小于1.0m（GB50016-7.2.3）",
        level="L1",
        func_id="DIM-087",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="m", operator=">=", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-8.1.2: 消防水源判定
    Clause(
        clause_id="GB50016-8.1.2",
        standard="GB 50016-2014",
        title="消防水源判定",
        text="建筑应设置消防水源（GB50016-8.1.2）",
        level="L1",
        func_id="EXIST-055",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-8.2.3: 自然排烟窗口面积判定
    Clause(
        clause_id="GB50016-8.2.3",
        standard="GB 50016-2014",
        title="自然排烟窗口面积判定",
        text="自然排烟窗口面积不应小于地面面积的2%（GB50016-8.2.3）",
        level="L1",
        func_id="AREA-011",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.02, unit="%", operator="ge", building_types={"civil": 0.02, "industrial": 0.02}
        ),
    ),
    # GB50016-6.4.1: 楼梯间首层直通室外判定
    Clause(
        clause_id="GB50016-6.4.1",
        standard="GB 50016-2014",
        title="楼梯间首层直通室外判定",
        text="疏散楼梯间首层应直通室外（GB50016-6.4.1）",
        level="L1",
        func_id="EXIST-065",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
]
