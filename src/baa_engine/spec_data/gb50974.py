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


GB50974_CLAUSES = [
    # 自动生成的规范条款（匹配现有原子函数）
    # GB50016-4.3.2: 消防水池有效容积判定
    Clause(
        clause_id="GB50974-4.3.2",
        standard="GB 50974-2014",
        title="消防水池有效容积判定",
        text="消防水池有效容积应满足火灾延续时间内消防用水量（GB50974-4.3.2）",
        level="L1",
        func_id="DIM-035",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=500.0,
            unit="m3",
            operator="ge",
            building_types={"civil": 500.0, "industrial": 500.0},
        ),
    ),
    # GB50016-4.3.6: 消防水池分格判定
    Clause(
        clause_id="GB50974-4.3.6",
        standard="GB 50974-2014",
        title="消防水池分格判定",
        text="消防水池总有效容积大于500m³时宜设两格能独立使用的消防水池（GB50974-4.3.6）",
        level="L1",
        func_id="COUNT-005",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="个", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-5.2.1: 高位消防水箱有效容积判定
    Clause(
        clause_id="GB50974-5.2.1",
        standard="GB 50974-2014",
        title="高位消防水箱有效容积判定",
        text="一类高层公共建筑高位消防水箱有效容积不应小于36m³（GB50974-5.2.1）",
        level="L1",
        func_id="DIM-036",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=36.0, unit="m3", operator="ge", building_types={"civil": 36.0, "industrial": 36.0}
        ),
    ),
    # GB50016-5.2.2: 消防水箱有效水位判定
    Clause(
        clause_id="GB50974-5.2.2",
        standard="GB 50974-2014",
        title="消防水箱有效水位判定",
        text="高位消防水箱最低有效水位应满足灭火设施压力要求（GB50974-5.2.2）",
        level="L1",
        func_id="DIM-037",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.0, unit="m", operator="ge", building_types={"civil": 2.0, "industrial": 2.0}
        ),
    ),
    # GB50016-5.3.2: 稳压泵流量判定
    Clause(
        clause_id="GB50974-5.3.2",
        standard="GB 50974-2014",
        title="稳压泵流量判定",
        text="消防给水稳压泵流量不应小于1.0L/s（GB50974-5.3.2）",
        level="L1",
        func_id="DIM-038",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="L/s", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-5.4.3: 水泵接合器数量判定
    Clause(
        clause_id="GB50974-5.4.3",
        standard="GB 50974-2014",
        title="水泵接合器数量判定",
        text="消防水泵接合器数量应按消防用水量计算确定（GB50974-5.4.3）",
        level="L1",
        func_id="COUNT-006",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="个", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-5.5.12: 消防水泵房排水判定
    Clause(
        clause_id="GB50974-5.5.12",
        standard="GB 50974-2014",
        title="消防水泵房排水判定",
        text="消防水泵房应设排水设施（GB50974-5.5.12）",
        level="L1",
        func_id="EXIST-025",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="有/无", operator="eq", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-6.1.8: 室外消火栓间距判定
    Clause(
        clause_id="GB50974-6.1.8",
        standard="GB 50974-2014",
        title="室外消火栓间距判定",
        text="室外消火栓布置间距不应大于120m（GB50974-6.1.8）",
        level="L1",
        func_id="DIST-011",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=120.0,
            unit="m",
            operator="le",
            building_types={"civil": 120.0, "industrial": 120.0},
        ),
    ),
    # GB50016-6.2.1: 室内消火栓间距判定
    Clause(
        clause_id="GB50974-6.2.1",
        standard="GB 50974-2014",
        title="室内消火栓间距判定",
        text="室内消火栓间距不应大于30m（GB50974-6.2.1）",
        level="L1",
        func_id="DIST-012",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30.0, unit="m", operator="le", building_types={"civil": 30.0, "industrial": 30.0}
        ),
    ),
    # GB50016-6.4.2: 消防水带长度判定
    Clause(
        clause_id="GB50974-6.4.2",
        standard="GB 50974-2014",
        title="消防水带长度判定",
        text="消防水带长度不宜大于25m（GB50974-6.4.2）",
        level="L1",
        func_id="DIM-039",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=25.0, unit="m", operator="le", building_types={"civil": 25.0, "industrial": 25.0}
        ),
    ),
    # GB50016-7.4.2: 消防水枪充实水柱判定
    Clause(
        clause_id="GB50974-7.4.2",
        standard="GB 50974-2014",
        title="消防水枪充实水柱判定",
        text="消防水枪充实水柱不应小于13m（GB50974-7.4.2）",
        level="L1",
        func_id="DIM-040",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=13.0, unit="m", operator="ge", building_types={"civil": 13.0, "industrial": 13.0}
        ),
    ),
    # GB50016-8.1.2: 消防给水管道压力判定
    Clause(
        clause_id="GB50974-8.1.2",
        standard="GB 50974-2014",
        title="消防给水管道压力判定",
        text="消防给水管道最低压力不应小于0.10MPa（GB50974-8.1.2）",
        level="L1",
        func_id="ATTR-008",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.1, unit="MPa", operator="ge", building_types={"civil": 0.1, "industrial": 0.1}
        ),
    ),
    # GB50016-9.3.1: 消防水泵流量判定
    Clause(
        clause_id="GB50974-9.3.1",
        standard="GB 50974-2014",
        title="消防水泵流量判定",
        text="消防水泵流量不应小于设计消防用水量（GB50974-9.3.1）",
        level="L1",
        func_id="DIM-041",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=20.0,
            unit="L/s",
            operator="ge",
            building_types={"civil": 20.0, "industrial": 20.0},
        ),
    ),
    # GB50016-11.0.4: 消防水泵启动时间判定
    Clause(
        clause_id="GB50974-11.0.4",
        standard="GB 50974-2014",
        title="消防水泵启动时间判定",
        text="消防水泵从接到启泵信号到正常运转时间不应大于2min（GB50974-11.0.4）",
        level="L1",
        func_id="DIM-042",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.0, unit="min", operator="le", building_types={"civil": 2.0, "industrial": 2.0}
        ),
    ),
    # GB50016-12.3.1: 消防管道管径判定
    Clause(
        clause_id="GB50974-12.3.1",
        standard="GB 50974-2014",
        title="消防管道管径判定",
        text="消防给水管道管径不应小于DN100（GB50974-12.3.1）",
        level="L1",
        func_id="DIM-043",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=100.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 100.0, "industrial": 100.0},
        ),
    ),
    # GB50016-5.1.12: 消防水泵吸水高度判定
    Clause(
        clause_id="GB50974-5.1.12",
        standard="GB 50974-2014",
        title="消防水泵吸水高度判定",
        text="消防水泵吸水高度不应大于6.0m（GB50974-5.1.12）",
        level="L1",
        func_id="DIM-044",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=6.0, unit="m", operator="le", building_types={"civil": 6.0, "industrial": 6.0}
        ),
    ),
    # GB50016-5.1.13: 消防水泵出水管压力判定
    Clause(
        clause_id="GB50974-5.1.13",
        standard="GB 50974-2014",
        title="消防水泵出水管压力判定",
        text="消防水泵出水管压力不应小于设计工作压力（GB50974-5.1.13）",
        level="L1",
        func_id="DIM-045",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.8, unit="MPa", operator="ge", building_types={"civil": 0.8, "industrial": 0.8}
        ),
    ),
    # GB50016-4.3.3: 消防水池进水管管径判定
    Clause(
        clause_id="GB50974-4.3.3",
        standard="GB 50974-2014",
        title="消防水池进水管管径判定",
        text="消防水池进水管管径不应小于DN100（GB50974-4.3.3）",
        level="L1",
        func_id="DIM-046",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=100.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 100.0, "industrial": 100.0},
        ),
    ),
    # GB50016-5.2.4: 消防水箱间温度判定
    Clause(
        clause_id="GB50974-5.2.4",
        standard="GB 50974-2014",
        title="消防水箱间温度判定",
        text="消防水箱间温度不应低于5℃（GB50974-5.2.4）",
        level="L1",
        func_id="DIM-047",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=5.0, unit="℃", operator="ge", building_types={"civil": 5.0, "industrial": 5.0}
        ),
    ),
    # GB50016-5.1.6: 消防水泵数量判定
    Clause(
        clause_id="GB50974-5.1.6",
        standard="GB 50974-2014",
        title="消防水泵数量判定",
        text="消防水泵应设置不少于2台（GB50974-5.1.6）",
        level="L1",
        func_id="COUNT-007",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="台", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-5.1.11: 消防水泵试水管判定
    Clause(
        clause_id="GB50974-5.1.11",
        standard="GB 50974-2014",
        title="消防水泵试水管判定",
        text="消防水泵应设置试水管（GB50974-5.1.11）",
        level="L1",
        func_id="EXIST-027",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="有/无", operator="eq", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-8.2.3: 消防给水管道材质判定
    Clause(
        clause_id="GB50974-8.2.3",
        standard="GB 50974-2014",
        title="消防给水管道材质判定",
        text="消防给水管道应采用热镀锌钢管等金属管材（GB50974-8.2.3）",
        level="L1",
        func_id="ATTR-009",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="级", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-4.3.5: 消防水池取水口高度判定
    Clause(
        clause_id="GB50974-4.3.5",
        standard="GB 50974-2014",
        title="消防水池取水口高度判定",
        text="消防水池取水口高度不宜大于6.0m（GB50974-4.3.5）",
        level="L1",
        func_id="DIM-051",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=6.0, unit="m", operator="le", building_types={"civil": 6.0, "industrial": 6.0}
        ),
    ),
    # GB50016-5.5.8: 消防水泵基础高度判定
    Clause(
        clause_id="GB50974-5.5.8",
        standard="GB 50974-2014",
        title="消防水泵基础高度判定",
        text="消防水泵基础高出地面不宜小于0.10m（GB50974-5.5.8）",
        level="L1",
        func_id="DIM-052",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.1, unit="m", operator="ge", building_types={"civil": 0.1, "industrial": 0.1}
        ),
    ),
    # GB50016-12.4.1: 消防给水管网试验压力判定
    Clause(
        clause_id="GB50974-12.4.1",
        standard="GB 50974-2014",
        title="消防给水管网试验压力判定",
        text="消防给水管网试压压力不应小于1.4MPa（GB50974-12.4.1）",
        level="L1",
        func_id="DIM-055",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.4, unit="MPa", operator="ge", building_types={"civil": 1.4, "industrial": 1.4}
        ),
    ),
    # GB50016-5.4.4: 消防水泵接合器数量下限判定
    Clause(
        clause_id="GB50974-5.4.4",
        standard="GB 50974-2014",
        title="消防水泵接合器数量下限判定",
        text="消防水泵接合器数量不应少于2个（GB50974-5.4.4）",
        level="L1",
        func_id="COUNT-009",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="个", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-7.4.5: 室内消火栓竖管数量判定
    Clause(
        clause_id="GB50974-7.4.5",
        standard="GB 50974-2014",
        title="室内消火栓竖管数量判定",
        text="室内消火栓竖管数量不应少于2根（GB50974-7.4.5）",
        level="L1",
        func_id="COUNT-010",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="根", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-5.4.5: 水泵接合器与门窗距离判定
    Clause(
        clause_id="GB50974-5.4.5",
        standard="GB 50974-2014",
        title="水泵接合器与门窗距离判定",
        text="水泵接合器距门窗洞口不宜小于2.0m（GB50974-5.4.5）",
        level="L1",
        func_id="DIST-015",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.0, unit="m", operator="ge", building_types={"civil": 2.0, "industrial": 2.0}
        ),
    ),
    # GB50016-11.0.1: 消防水泵启泵按钮判定
    Clause(
        clause_id="GB50974-11.0.1",
        standard="GB 50974-2014",
        title="消防水泵启泵按钮判定",
        text="消防水泵应设置现场手动启泵按钮（GB50974-11.0.1）",
        level="L1",
        func_id="EXIST-030",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="有/无", operator="eq", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-4.3.8: 消防水池水位显示判定
    Clause(
        clause_id="GB50974-4.3.8",
        standard="GB 50974-2014",
        title="消防水池水位显示判定",
        text="消防水池应设置就地水位显示装置（GB50974-4.3.8）",
        level="L1",
        func_id="EXIST-031",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="有/无", operator="eq", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-5.2.3: 消防水箱进水压力（高位水箱）
    Clause(
        clause_id="GB50974-5.2.3",
        standard="GB 50974-2014",
        title="消防水箱进水压力（高位水箱）",
        text="高位消防水箱进水压力不应大于0.1MPa（GB50974-5.2.3）",
        level="L1",
        func_id="DIM-059",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.1, unit="MPa", operator="le", building_types={"civil": 0.1, "industrial": 0.1}
        ),
    ),
    # GB50016-5.2.5: 消防水箱最高水位
    Clause(
        clause_id="GB50974-5.2.5",
        standard="GB 50974-2014",
        title="消防水箱最高水位",
        text="消防水箱最高水位不应低于有效水深（GB50974-5.2.5）",
        level="L1",
        func_id="DIM-060",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.7, unit="m", operator="ge", building_types={"civil": 0.7, "industrial": 0.7}
        ),
    ),
    # GB50016-4.3.3: 消防水池储水量下限（消火栓系统）
    Clause(
        clause_id="GB50974-4.3.3-2",
        standard="GB 50974-2014",
        title="消防水池储水量下限（消火栓系统）",
        text="室外消火栓系统消防水池有效储水量不应小于100m³（GB50974-4.3.3-2）",
        level="L1",
        func_id="DIM-061",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=100.0,
            unit="m³",
            operator="ge",
            building_types={"civil": 100.0, "industrial": 100.0},
        ),
    ),
    # GB50016-4.3.3: 消防水池储水量下限（自喷系统）
    Clause(
        clause_id="GB50974-4.3.3-3",
        standard="GB 50974-2014",
        title="消防水池储水量下限（自喷系统）",
        text="室内自动喷水灭火系统消防水池有效储水量不应小于150m³（GB50974-4.3.3-3）",
        level="L1",
        func_id="DIM-062",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=150.0,
            unit="m³",
            operator="ge",
            building_types={"civil": 150.0, "industrial": 150.0},
        ),
    ),
    # GB50016-5.1.15: 消防水箱容积（临时高压系统）
    Clause(
        clause_id="GB50974-5.1.15",
        standard="GB 50974-2014",
        title="消防水箱容积（临时高压系统）",
        text="临时高压系统消防水箱有效容积不应小于100m³（GB50974-5.1.15）",
        level="L1",
        func_id="DIM-063",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=100.0,
            unit="m³",
            operator="ge",
            building_types={"civil": 100.0, "industrial": 100.0},
        ),
    ),
    # GB50016-5.1.16: 消防水箱出水流量
    Clause(
        clause_id="GB50974-5.1.16",
        standard="GB 50974-2014",
        title="消防水箱出水流量",
        text="消防水箱出水流量不应小于10L/s（GB50974-5.1.16）",
        level="L1",
        func_id="DIM-064",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=10.0,
            unit="L/s",
            operator="ge",
            building_types={"civil": 10.0, "industrial": 10.0},
        ),
    ),
    # GB50016-5.2.6: 消防水箱间与卧室距离
    Clause(
        clause_id="GB50974-5.2.6",
        standard="GB 50974-2014",
        title="消防水箱间与卧室距离",
        text="消防水箱间不应设置于卧室上方或相邻（GB50974-5.2.6）",
        level="L1",
        func_id="DIST-017",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.0, unit="m", operator="lt", building_types={"civil": 0.0, "industrial": 0.0}
        ),
    ),
    # GB50016-5.5.4: 消防水泵房防火分隔距离
    Clause(
        clause_id="GB50974-5.5.4",
        standard="GB 50974-2014",
        title="消防水泵房防火分隔距离",
        text="消防水泵房与人员密集场所应设防火隔墙分隔（GB50974-5.5.4）",
        level="L1",
        func_id="DIST-018",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=6.0, unit="m", operator="ge", building_types={"civil": 6.0, "industrial": 6.0}
        ),
    ),
    # GB50016-4.3.7: 消防水池与建筑物距离
    Clause(
        clause_id="GB50974-4.3.7",
        standard="GB 50974-2014",
        title="消防水池与建筑物距离",
        text="室外消防水池与民用建筑距离不宜小于25m（GB50974-4.3.7）",
        level="L1",
        func_id="DIST-019",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=25.0, unit="m", operator="ge", building_types={"civil": 25.0, "industrial": 25.0}
        ),
    ),
    # GB50016-5.1.6: 消防水泵出口流量下限（临时高压）
    Clause(
        clause_id="GB50974-5.1.6-2",
        standard="GB 50974-2014",
        title="消防水泵出口流量下限（临时高压）",
        text="临时高压系统消防水泵出水流量不应少于2路（GB50974-5.1.6）",
        level="L1",
        func_id="COUNT-011",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="路", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-5.1.6: 消防给水系统备用泵数量
    Clause(
        clause_id="GB50974-5.1.6-1",
        standard="GB 50974-2014",
        title="消防给水系统备用泵数量",
        text="消防给水系统应设1台备用泵（GB50974-5.1.6）",
        level="L1",
        func_id="COUNT-012",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="台", operator="ge", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-5.2.7: 消防水箱间消防给水管道阀门
    Clause(
        clause_id="GB50974-5.2.7",
        standard="GB 50974-2014",
        title="消防水箱间消防给水管道阀门",
        text="消防水箱间进水管道应设止回阀（GB50974-5.2.7）",
        level="L1",
        func_id="EXIST-032",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-5.5.5: 消防水泵房排水设施
    Clause(
        clause_id="GB50974-5.5.5",
        standard="GB 50974-2014",
        title="消防水泵房排水设施",
        text="消防水泵房应设排水设施（GB50974-5.5.5）",
        level="L1",
        func_id="EXIST-033",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-11.0.14: 消防水泵房备用电源切换装置
    Clause(
        clause_id="GB50974-11.0.14",
        standard="GB 50974-2014",
        title="消防水泵房备用电源切换装置",
        text="消防水泵房应设备用电源切换装置（GB50974-11.0.14）",
        level="L1",
        func_id="EXIST-034",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-5.4.1: 消防水泵接合器设置判定
    Clause(
        clause_id="GB50974-5.4.1",
        standard="GB 50974-2014",
        title="消防水泵接合器设置判定",
        text="高层民用建筑应设消防水泵接合器（GB50974-5.4.1）",
        level="L1",
        func_id="EXIST-038",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="个", operator="ge", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-4.3.1: 消防水池最小容积判定
    Clause(
        clause_id="GB50974-4.3.1",
        standard="GB 50974-2014",
        title="消防水池最小容积判定",
        text="消防水池最小有效容积不应小于100m³（GB50974-4.3.1）",
        level="L1",
        func_id="DIM-077",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=100.0,
            unit="m³",
            operator="ge",
            building_types={"civil": 100.0, "industrial": 100.0},
        ),
    ),
    # GB50016-7.4.10: 室内消火栓间距判定
    Clause(
        clause_id="GB50974-7.4.10",
        standard="GB 50974-2014",
        title="室内消火栓间距判定",
        text="室内消火栓最大间距不应大于30m（GB50974-7.4.10）",
        level="L1",
        func_id="DIST-022",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30.0, unit="m", operator="le", building_types={"civil": 30.0, "industrial": 30.0}
        ),
    ),
    # GB50016-7.3.1: 室外消火栓间距判定
    Clause(
        clause_id="GB50974-7.3.1",
        standard="GB 50974-2014",
        title="室外消火栓间距判定",
        text="室外消火栓最大间距不应大于120m（GB50974-7.3.1）",
        level="L1",
        func_id="DIST-023",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=120.0,
            unit="m",
            operator="le",
            building_types={"civil": 120.0, "industrial": 120.0},
        ),
    ),
    # GB50016-7.4.1: 消火栓间距判定
    Clause(
        clause_id="GB50974-7.4.1",
        standard="GB 50974-2014",
        title="消火栓间距判定",
        text="室内消火栓间距不应大于30m（GB50974-7.4.1）",
        level="L1",
        func_id="DIST-025",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30.0, unit="m", operator="<=", building_types={"civil": 30.0, "industrial": 30.0}
        ),
    ),
    # GB50016-7.4.3: 消火栓保护半径判定
    Clause(
        clause_id="GB50974-7.4.3",
        standard="GB 50974-2014",
        title="消火栓保护半径判定",
        text="室内消火栓保护半径不应大于25m（GB50974-7.4.3）",
        level="L1",
        func_id="DIST-026",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=25.0, unit="m", operator="<=", building_types={"civil": 25.0, "industrial": 25.0}
        ),
    ),
    # GB50016-7.4.4: 消火栓出口压力判定
    Clause(
        clause_id="GB50974-7.4.4",
        standard="GB 50974-2014",
        title="消火栓出口压力判定",
        text="消火栓栓口动压不应大于0.50MPa（GB50974-7.4.4）",
        level="L1",
        func_id="ATTR-012",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.5, unit="MPa", operator="<=", building_types={"civil": 0.5, "industrial": 0.5}
        ),
    ),
    # GB50016-7.4.6: 消防软管卷盘判定
    Clause(
        clause_id="GB50974-7.4.6",
        standard="GB 50974-2014",
        title="消防软管卷盘判定",
        text="人员密集场所应设消防软管卷盘（GB50974-7.4.6）",
        level="L1",
        func_id="EXIST-057",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-7.4.7: 消防水喉判定
    Clause(
        clause_id="GB50974-7.4.7",
        standard="GB 50974-2014",
        title="消防水喉判定",
        text="高层民用建筑应设消防水喉（GB50974-7.4.7）",
        level="L1",
        func_id="EXIST-058",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-7.4.12: 消防水带长度判定
    Clause(
        clause_id="GB50974-7.4.12",
        standard="GB 50974-2014",
        title="消防水带长度判定",
        text="消防水带长度不应超过25m（GB50974-7.4.12）",
        level="L1",
        func_id="DIM-093",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=25.0, unit="m", operator="<=", building_types={"civil": 25.0, "industrial": 25.0}
        ),
    ),
]
