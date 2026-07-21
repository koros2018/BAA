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


GB50763_CLAUSES = [
    # 自动生成的规范条款（匹配现有原子函数）
    # GB50016-3.3.2: 轮椅坡道坡度判定
    Clause(
        clause_id="GB50763-3.3.2",
        standard="GB 50763-2012",
        title="轮椅坡道坡度判定",
        text="坡道坡度不应大于1:12(8.33%)",
        level="L1",
        func_id="ACCESS-001",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=8.33, unit="%", operator="<=", building_types={"civil": 8.33, "industrial": 8.33}
        ),
    ),
    # GB50016-3.3.3: 轮椅坡道宽度判定
    Clause(
        clause_id="GB50763-3.3.3",
        standard="GB 50763-2012",
        title="轮椅坡道宽度判定",
        text="坡道净宽不应小于1.20m",
        level="L1",
        func_id="ACCESS-002",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.2, unit="m", operator=">=", building_types={"civil": 1.2, "industrial": 1.2}
        ),
    ),
    # GB50016-3.5.2: 无障碍出入口宽度判定
    Clause(
        clause_id="GB50763-3.5.2",
        standard="GB 50763-2012",
        title="无障碍出入口宽度判定",
        text="出入口净宽不应小于0.90m",
        level="L1",
        func_id="ACCESS-003",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.9, unit="m", operator=">=", building_types={"civil": 0.9, "industrial": 0.9}
        ),
    ),
    # GB50016-3.6.1: 无障碍通道宽度判定
    Clause(
        clause_id="GB50763-3.6.1",
        standard="GB 50763-2012",
        title="无障碍通道宽度判定",
        text="通道净宽不应小于1.20m",
        level="L1",
        func_id="ACCESS-004",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.2, unit="m", operator=">=", building_types={"civil": 1.2, "industrial": 1.2}
        ),
    ),
    # GB50016-3.8.1: 扶手设置判定
    Clause(
        clause_id="GB50763-3.8.1",
        standard="GB 50763-2012",
        title="扶手设置判定",
        text="坡道/台阶两侧应设扶手",
        level="L1",
        func_id="ACCESS-005",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="有", operator="==", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-3.7.1: 无障碍电梯判定
    Clause(
        clause_id="GB50763-3.7.1",
        standard="GB 50763-2012",
        title="无障碍电梯判定",
        text="二层及以上应设无障碍电梯",
        level="L1",
        func_id="ACCESS-006",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="有", operator="==", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-3.11.2: 无障碍停车位判定
    Clause(
        clause_id="GB50763-3.11.2",
        standard="GB 50763-2012",
        title="无障碍停车位判定",
        text="应设不少于总车位2%的无障碍车位",
        level="L1",
        func_id="ACCESS-007",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.02,
            unit="比例",
            operator=">=",
            building_types={"civil": 0.02, "industrial": 0.02},
        ),
    ),
    # GB50016-3.9.1: 无障碍卫生间判定
    Clause(
        clause_id="GB50763-3.9.1",
        standard="GB 50763-2012",
        title="无障碍卫生间判定",
        text="应设无障碍卫生间",
        level="L1",
        func_id="ACCESS-008",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="有", operator="==", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-3.8.2: 轮椅回转空间判定
    Clause(
        clause_id="GB50763-3.8.2",
        standard="GB 50763-2012",
        title="轮椅回转空间判定",
        text="轮椅回转直径不应小于1.50m",
        level="L1",
        func_id="ACCESS-009",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.5, unit="m", operator=">=", building_types={"civil": 1.5, "industrial": 1.5}
        ),
    ),
    # GB50016-3.2.1: 盲道设置判定
    Clause(
        clause_id="GB50763-3.2.1",
        standard="GB 50763-2012",
        title="盲道设置判定",
        text="主要流线应设盲道",
        level="L1",
        func_id="ACCESS-010",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="有", operator="==", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-3.7.2: 无障碍电梯门洞宽度判定
    Clause(
        clause_id="GB50763-3.7.2",
        standard="GB 50763-2012",
        title="无障碍电梯门洞宽度判定",
        text="无障碍电梯门洞净宽度不应小于0.90m（GB50763-3.7.2）",
        level="L1",
        func_id="DIM-049",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.9, unit="m", operator="ge", building_types={"civil": 0.9, "industrial": 0.9}
        ),
    ),
    # GB50016-3.11.1: 无障碍停车位数量判定
    Clause(
        clause_id="GB50763-3.11.1",
        standard="GB 50763-2012",
        title="无障碍停车位数量判定",
        text="应设不少于总停车位数2%的无障碍停车位（GB50763-3.11.1）",
        level="L1",
        func_id="COUNT-008",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.02,
            unit="比例",
            operator="ge",
            building_types={"civil": 0.02, "industrial": 0.02},
        ),
    ),
    # GB50016-3.6.2: 无障碍楼梯扶手判定
    Clause(
        clause_id="GB50763-3.6.2",
        standard="GB 50763-2012",
        title="无障碍楼梯扶手判定",
        text="无障碍楼梯两侧应设扶手（GB50763-3.6.2）",
        level="L1",
        func_id="EXIST-028",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="有/无", operator="eq", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-3.16.1: 无障碍标识判定
    Clause(
        clause_id="GB50763-3.16.1",
        standard="GB 50763-2012",
        title="无障碍标识判定",
        text="无障碍设施处应设无障碍标识（GB50763-3.16.1）",
        level="L1",
        func_id="EXIST-029",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="有/无", operator="eq", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-3.9.2: 无障碍卫生间距离判定
    Clause(
        clause_id="GB50763-3.9.2",
        standard="GB 50763-2012",
        title="无障碍卫生间距离判定",
        text="无障碍卫生间距最近无障碍出入口距离不应大于30m（GB50763-3.9.2）",
        level="L1",
        func_id="DIST-014",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30.0, unit="m", operator="le", building_types={"civil": 30.0, "industrial": 30.0}
        ),
    ),
    # GB50016-3.13.1: 无障碍住房面积判定
    Clause(
        clause_id="GB50763-3.13.1",
        standard="GB 50763-2012",
        title="无障碍住房面积判定",
        text="无障碍住房套内使用面积不应小于35.0sqm（GB50763-3.13.1）",
        level="L1",
        func_id="AREA-006",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=35.0,
            unit="sqm",
            operator="ge",
            building_types={"civil": 35.0, "industrial": 35.0},
        ),
    ),
    # GB50016-3.13.2: 无障碍住房卧室面积
    Clause(
        clause_id="GB50763-3.13.2",
        standard="GB 50763-2012",
        title="无障碍住房卧室面积",
        text="无障碍住房卧室面积不应小于9㎡（GB50763-3.13.2）",
        level="L1",
        func_id="AREA-008",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=9.0, unit="m²", operator="ge", building_types={"civil": 9.0, "industrial": 9.0}
        ),
    ),
    # GB50016-3.7.2: 无障碍电梯轿厢深度
    Clause(
        clause_id="GB50763-3.7.2-2",
        standard="GB 50763-2012",
        title="无障碍电梯轿厢深度",
        text="无障碍电梯轿厢深度不应小于1.5m（GB50763-3.7.2）",
        level="L1",
        func_id="EXIST-035",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-3.9.6: 无障碍卫生间紧急呼叫按钮
    Clause(
        clause_id="GB50763-3.9.6",
        standard="GB 50763-2012",
        title="无障碍卫生间紧急呼叫按钮",
        text="无障碍卫生间应设紧急呼叫按钮（GB50763-3.9.6）",
        level="L1",
        func_id="EXIST-036",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-3.2.3: 盲道与障碍物距离判定
    Clause(
        clause_id="GB50763-3.2.3",
        standard="GB 50763-2012",
        title="盲道与障碍物距离判定",
        text="盲道与障碍物距离不应小于0.25m（GB50763-3.2.3）",
        level="L1",
        func_id="ACCESS-012",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.25, unit="m", operator="ge", building_types={"civil": 0.25, "industrial": 0.25}
        ),
    ),
    # GB50016-3.3.4: 无障碍坡道休息平台深度判定
    Clause(
        clause_id="GB50763-3.3.4",
        standard="GB 50763-2012",
        title="无障碍坡道休息平台深度判定",
        text="无障碍坡道休息平台深度不应小于1.50m（GB50763-3.3.4）",
        level="L1",
        func_id="ACCESS-013",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.5, unit="m", operator="ge", building_types={"civil": 1.5, "industrial": 1.5}
        ),
    ),
    # GB50016-3.6.3: 无障碍楼梯踏步宽度判定
    Clause(
        clause_id="GB50763-3.6.3",
        standard="GB 50763-2012",
        title="无障碍楼梯踏步宽度判定",
        text="无障碍楼梯踏步宽度不应小于0.28m（GB50763-3.6.3）",
        level="L1",
        func_id="ACCESS-014",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.28, unit="m", operator="ge", building_types={"civil": 0.28, "industrial": 0.28}
        ),
    ),
    # GB50016-7.6.1: 无障碍客房数量判定
    Clause(
        clause_id="GB50763-7.6.1",
        standard="GB 50763-2012",
        title="无障碍客房数量判定",
        text="设有客房的旅馆应设不少于总客房数2%的无障碍客房（GB50763-7.6.1）",
        level="L1",
        func_id="ACCESS-016",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.02, unit="%", operator="ge", building_types={"civil": 0.02, "industrial": 0.02}
        ),
    ),
    # GB50016-7.7.1: 无障碍观众席数量判定
    Clause(
        clause_id="GB50763-7.7.1",
        standard="GB 50763-2012",
        title="无障碍观众席数量判定",
        text="设有座位的公共场所应设不少于总座位数0.2%的无障碍观众席（GB50763-7.7.1）",
        level="L1",
        func_id="ACCESS-017",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.002,
            unit="%",
            operator="ge",
            building_types={"civil": 0.002, "industrial": 0.002},
        ),
    ),
    # GB50016-3.1.2: 缘石坡道宽度判定
    Clause(
        clause_id="GB50763-3.1.2",
        standard="GB 50763-2012",
        title="缘石坡道宽度判定",
        text="缘石坡道宽度不应小于1.20m（GB50763-3.1.2）",
        level="L1",
        func_id="ACCESS-018",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.2, unit="m", operator="ge", building_types={"civil": 1.2, "industrial": 1.2}
        ),
    ),
    # GB50016-3.6.4: 无障碍扶手高度判定
    Clause(
        clause_id="GB50763-3.6.4",
        standard="GB 50763-2012",
        title="无障碍扶手高度判定",
        text="无障碍楼梯扶手高度不应小于0.85m，无障碍坡道扶手高度不应小于0.85m（GB50763-3.6.4）",
        level="L1",
        func_id="ACCESS-019",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.85, unit="m", operator="ge", building_types={"civil": 0.85, "industrial": 0.85}
        ),
    ),
    # GB50016-3.9.3: 无障碍厕所洗手盆深度判定
    Clause(
        clause_id="GB50763-3.9.3",
        standard="GB 50763-2012",
        title="无障碍厕所洗手盆深度判定",
        text="无障碍厕所洗手盆中心距侧墙不应小于0.55m（GB50763-3.9.3）",
        level="L1",
        func_id="ACCESS-020",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.55, unit="m", operator="ge", building_types={"civil": 0.55, "industrial": 0.55}
        ),
    ),
    # GB50016-3.8.3: 无障碍通道门宽度判定
    Clause(
        clause_id="GB50763-3.8.3",
        standard="GB 50763-2012",
        title="无障碍通道门宽度判定",
        text="无障碍通道上的门净宽不应小于0.80m（GB50763-3.8.3）",
        level="L1",
        func_id="DIM-092",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.8, unit="m", operator=">=", building_types={"civil": 0.8, "industrial": 0.8}
        ),
    ),
    # GB50016-3.12.1: 无障碍厕所求助按钮判定
    Clause(
        clause_id="GB50763-3.12.1",
        standard="GB 50763-2012",
        title="无障碍厕所求助按钮判定",
        text="无障碍厕所应设求助呼叫按钮（GB50763-3.12.1）",
        level="L1",
        func_id="EXIST-066",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
]
