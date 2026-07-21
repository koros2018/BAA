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


GB50067_CLAUSES = [
    # 自动生成的规范条款（匹配现有原子函数）
    # GB50016-6.0.10: 汽车疏散坡道宽度判定
    Clause(
        clause_id="GB50067-6.0.10",
        standard="GB 50067-2014",
        title="汽车疏散坡道宽度判定",
        text="汽车疏散坡道宽度不应小于4.0m，双车道不应小于7.0m（GB50067-6.0.10）",
        level="L1",
        func_id="DIM-065",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=4.0, unit="m", operator="ge", building_types={"civil": 4.0, "industrial": 4.0}
        ),
    ),
    # GB50016-4.1.5: 停车位宽度判定
    Clause(
        clause_id="GB50067-4.1.5",
        standard="GB 50067-2014",
        title="停车位宽度判定",
        text="平行停车位宽度不应小于2.4m，垂直停车位宽度不应小于2.5m（GB50067-4.1.5）",
        level="L1",
        func_id="DIM-066",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.4, unit="m", operator="ge", building_types={"civil": 2.4, "industrial": 2.4}
        ),
    ),
    # GB50016-4.1.6: 汽车通道宽度判定
    Clause(
        clause_id="GB50067-4.1.6",
        standard="GB 50067-2014",
        title="汽车通道宽度判定",
        text="汽车库内汽车通道宽度不应小于5.5m（GB50067-4.1.6）",
        level="L1",
        func_id="DIM-068",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=5.5, unit="m", operator="ge", building_types={"civil": 5.5, "industrial": 5.5}
        ),
    ),
    # GB50016-5.1.1: 汽车库防火分区面积判定
    Clause(
        clause_id="GB50067-5.1.1",
        standard="GB 50067-2014",
        title="汽车库防火分区面积判定",
        text="地下汽车库防火分区最大允许面积不应大于2000㎡（GB50067-5.1.1）",
        level="L1",
        func_id="DIM-069",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2000.0,
            unit="㎡",
            operator="le",
            building_types={"civil": 2000.0, "industrial": 2000.0},
        ),
    ),
    # GB50016-6.0.3: 汽车库疏散楼梯宽度判定
    Clause(
        clause_id="GB50067-6.0.3",
        standard="GB 50067-2014",
        title="汽车库疏散楼梯宽度判定",
        text="汽车库内疏散楼梯净宽度不应小于1.1m（GB50067-6.0.3）",
        level="L1",
        func_id="DIM-071",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.1, unit="m", operator="ge", building_types={"civil": 1.1, "industrial": 1.1}
        ),
    ),
    # GB50016-6.0.5: 汽车库疏散距离判定
    Clause(
        clause_id="GB50067-6.0.5",
        standard="GB 50067-2014",
        title="汽车库疏散距离判定",
        text="汽车库内最远点到疏散出口距离不应大于45m（GB50067-6.0.5）",
        level="L1",
        func_id="DIST-020",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=45.0, unit="m", operator="le", building_types={"civil": 45.0, "industrial": 45.0}
        ),
    ),
    # GB50016-4.2.1: 汽车库与相邻建筑防火间距判定
    Clause(
        clause_id="GB50067-4.2.1",
        standard="GB 50067-2014",
        title="汽车库与相邻建筑防火间距判定",
        text="汽车库与相邻建筑的防火间距不应小于10m（GB50067-4.2.1）",
        level="L1",
        func_id="DIST-021",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=10.0, unit="m", operator="ge", building_types={"civil": 10.0, "industrial": 10.0}
        ),
    ),
    # GB50016-7.1.1: 汽车库消防给水判定
    Clause(
        clause_id="GB50067-7.1.1",
        standard="GB 50067-2014",
        title="汽车库消防给水判定",
        text="汽车库应设置消防给水系统（GB50067-7.1.1）",
        level="L1",
        func_id="EXIST-046",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="", operator="eq", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-7.2.1: 汽车库自动喷水灭火系统判定
    Clause(
        clause_id="GB50067-7.2.1",
        standard="GB 50067-2014",
        title="汽车库自动喷水灭火系统判定",
        text="地下汽车库应设置自动喷水灭火系统（GB50067-7.2.1）",
        level="L1",
        func_id="EXIST-047",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="", operator="eq", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-9.0.7: 汽车库火灾报警系统判定
    Clause(
        clause_id="GB50067-9.0.7",
        standard="GB 50067-2014",
        title="汽车库火灾报警系统判定",
        text="一、二类汽车库应设置火灾自动报警系统（GB50067-9.0.7）",
        level="L1",
        func_id="EXIST-048",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="", operator="eq", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-8.2.1: 汽车库排烟设施判定
    Clause(
        clause_id="GB50067-8.2.1",
        standard="GB 50067-2014",
        title="汽车库排烟设施判定",
        text="地下汽车库应设置排烟设施（GB50067-8.2.1）",
        level="L1",
        func_id="EXIST-049",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="", operator="eq", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-6.0.2: 汽车库疏散出口数量判定
    Clause(
        clause_id="GB50067-6.0.2",
        standard="GB 50067-2014",
        title="汽车库疏散出口数量判定",
        text="汽车库每个防火分区安全出口不应少于2个（GB50067-6.0.2）",
        level="L1",
        func_id="COUNT-013",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="个", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-5.1.2: 汽车库防火卷帘判定
    Clause(
        clause_id="GB50067-5.1.2",
        standard="GB 50067-2014",
        title="汽车库防火卷帘判定",
        text="汽车库防火分区间的防火卷帘耐火极限不应低于3.00h（GB50067-5.1.2）",
        level="L1",
        func_id="EXIST-063",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-5.1.4: 汽车库自动灭火分区面积判定
    Clause(
        clause_id="GB50067-5.1.4",
        standard="GB 50067-2014",
        title="汽车库自动灭火分区面积判定",
        text="设有自动灭火系统时，汽车库防火分区面积可增加1倍（GB50067-5.1.4）",
        level="L1",
        func_id="DIM-091",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=4000.0,
            unit="㎡",
            operator="<=",
            building_types={"civil": 4000.0, "industrial": 4000.0},
        ),
    ),
    # GB50016-6.0.6: 汽车库封闭楼梯间判定
    Clause(
        clause_id="GB50067-6.0.6",
        standard="GB 50067-2014",
        title="汽车库封闭楼梯间判定",
        text="汽车库疏散楼梯应设封闭楼梯间（GB50067-6.0.6）",
        level="L1",
        func_id="EXIST-064",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-8.2.2: 汽车库排烟量判定
    Clause(
        clause_id="GB50067-8.2.2",
        standard="GB 50067-2014",
        title="汽车库排烟量判定",
        text="汽车库排烟量不应小于30000m³/h（GB50067-8.2.2）",
        level="L1",
        func_id="AREA-012",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30000.0,
            unit="m³/h",
            operator=">=",
            building_types={"civil": 30000.0, "industrial": 30000.0},
        ),
    ),
]
