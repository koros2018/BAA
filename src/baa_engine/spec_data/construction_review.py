"""
施工图审查深度标准（P48）

覆盖 GB 50001~50003、GB/T 50100、HG/T 20519 等施工图纸深度要求，
按"图样完整性 / 标注完整性 / 专业协调性"三大维度组织。
每个审查项含：
- 深度等级 (L1=结构完整性 / L2=标注完整性 / L3=专业协调)
- 适用专业 (arch / struct / mech / elec / plumb)
- 检查方式 (auto / manual / ai)
- 关联原子函数 ID（有则接入审查流程，无则记录为人工项）
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional

__all__ = ["CONSTRUCTION_REVIEW_ITEMS", "get_construction_review_items"]


@dataclass
class ConstructionReviewItem:
    """施工图审查深度单项"""

    item_id: str  # 例: CD-001
    category: str  # completeness / annotation / coordination
    major: str  # arch / struct / mech / elec / plumb
    title: str  # 审查项名称
    description: str  # 详细描述
    standard_ref: str  # 规范/图集编号
    level: str  # L1 / L2 / L3
    check_method: str  # auto / manual / ai
    func_id: Optional[str] = None  # 关联原子函数
    weight: float = 1.0  # 审查权重（用于评分）


CONSTRUCTION_REVIEW_ITEMS = [
    # ══════════════════════════════════════════════════════════
    # L1: 图样完整性 — 各专业图纸是否齐全
    # ══════════════════════════════════════════════════════════
    ConstructionReviewItem(
        item_id="CD-001",
        category="completeness",
        major="arch",
        title="建筑平面图完整性",
        description="每层均应绘制完整的平面图，含平面尺寸标注、轴线编号、房间名称",
        standard_ref="GB/T 50104-2010 §3.1",
        level="L1",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-002",
        category="completeness",
        major="struct",
        title="结构平面图完整性",
        description="结构平面图应覆盖梁/柱/板/墙/基础，与建筑图轴线一致",
        standard_ref="GB 50009-2012 §3.2",
        level="L1",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-003",
        category="completeness",
        major="mech",
        title="暖通平面图完整性",
        description="含风管/水管走向、设备布置、风阀/防火阀位置",
        standard_ref="GB 50736-2012 §3.3",
        level="L1",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-004",
        category="completeness",
        major="elec",
        title="电气平面图完整性",
        description="含配电箱位置、线缆走向、开关插座布置、照明回路",
        standard_ref="GB 50303-2015 §3.1",
        level="L1",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-005",
        category="completeness",
        major="plumb",
        title="给排水平面图完整性",
        description="含给水管/排水管走向、管径、立管位置、卫生间/厨房管线",
        standard_ref="GB 50242-2002 §3.1",
        level="L1",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-006",
        category="completeness",
        major="arch",
        title="立面图完整性",
        description="建筑应至少含四个方向立面图，含标高、材质标注",
        standard_ref="GB/T 50104-2010 §3.2",
        level="L1",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-007",
        category="completeness",
        major="arch",
        title="剖面图完整性",
        description="应含关键剖面图，展示楼层标高、墙体材质、门窗标高",
        standard_ref="GB/T 50104-2010 §3.3",
        level="L1",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-008",
        category="completeness",
        major="struct",
        title="结构详图完整性",
        description="关键节点（梁柱节点/基础/楼梯/悬挑结构）应有详图",
        standard_ref="GB 50009-2012 §3.5",
        level="L1",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-009",
        category="completeness",
        major="arch",
        title="图纸目录",
        description="项目应包含完整的图纸目录，含图号/图名/比例/版次",
        standard_ref="GB/T 50100-2014 §4.1",
        level="L1",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-010",
        category="completeness",
        major="arch",
        title="设计说明",
        description="各工种应包含设计说明，含材料做法表/工程量汇总表",
        standard_ref="GB/T 50100-2014 §5.1",
        level="L1",
        check_method="manual",
    ),
    # ══════════════════════════════════════════════════════════
    # L2: 标注完整性 — 尺寸/标高/文字标注是否齐全
    # ══════════════════════════════════════════════════════════
    ConstructionReviewItem(
        item_id="CD-011",
        category="annotation",
        major="arch",
        title="平面尺寸标注完整性",
        description="每层平面图应有三道尺寸（细部/轴线/总长），精度 ≤5mm",
        standard_ref="GB/T 50104-2010 §4.2",
        level="L2",
        check_method="auto",
        func_id="DIM-001",
    ),
    ConstructionReviewItem(
        item_id="CD-012",
        category="annotation",
        major="arch",
        title="标高标注完整性",
        description="所有楼层/标高处应有标高符号及数值",
        standard_ref="GB/T 50104-2010 §4.3",
        level="L2",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-013",
        category="annotation",
        major="struct",
        title="结构构件编号",
        description="梁/柱/板应有统一的构件编号，与结构详图对应",
        standard_ref="GB 50009-2012 §4.1",
        level="L2",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-014",
        category="annotation",
        major="arch",
        title="门窗编号与门窗表",
        description="门窗应有统一编号，与门窗表/详图一致",
        standard_ref="GB/T 50104-2010 §5.1",
        level="L2",
        check_method="auto",
        func_id="DIM-002",
    ),
    ConstructionReviewItem(
        item_id="CD-015",
        category="annotation",
        major="arch",
        title="房间名称与面积",
        description="每个房间应标注房间名称及净面积",
        standard_ref="GB/T 50104-2010 §5.2",
        level="L2",
        check_method="auto",
        func_id="AREA-001",
    ),
    ConstructionReviewItem(
        item_id="CD-016",
        category="annotation",
        major="struct",
        title="配筋标注",
        description="梁/柱/板钢筋应有完整标注，含型号/数量/间距",
        standard_ref="GB 50009-2012 §5.3",
        level="L2",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-017",
        category="annotation",
        major="mech",
        title="管道标高与坡度",
        description="给排水/风管应有标高及坡度标注",
        standard_ref="GB 50736-2012 §4.2",
        level="L2",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-018",
        category="annotation",
        major="elec",
        title="电缆桥架及线路标注",
        description="电缆桥架/线槽应有规格/标高/编号标注",
        standard_ref="GB 50303-2015 §4.2",
        level="L2",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-019",
        category="annotation",
        major="arch",
        title="轴线编号连续性",
        description="轴线编号应连续，不跳号不重号，跨图对应一致",
        standard_ref="GB/T 50104-2010 §3.1",
        level="L2",
        check_method="auto",
        func_id="COUNT-001",
    ),
    ConstructionReviewItem(
        item_id="CD-020",
        category="annotation",
        major="arch",
        title="图例说明",
        description="每张图纸应含图例，含填充图案/符号/线型说明",
        standard_ref="GB/T 50104-2010 §6.1",
        level="L2",
        check_method="manual",
    ),
    # ══════════════════════════════════════════════════════════
    # L3: 专业协调性 — 多专业图纸之间是否一致
    # ══════════════════════════════════════════════════════════
    ConstructionReviewItem(
        item_id="CD-021",
        category="coordination",
        major="arch",
        title="建筑-结构轴线一致性",
        description="建筑图与结构图的轴线/柱网应完全一致",
        standard_ref="GB 50009-2012 §3.1",
        level="L3",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-022",
        category="coordination",
        major="arch",
        title="结构-机电开洞一致性",
        description="结构梁/板开洞与机电管线走向一致，预留洞口位置尺寸匹配",
        standard_ref="GB 50009-2012 §4.5",
        level="L3",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-023",
        category="coordination",
        major="arch",
        title="设备管线综合排布",
        description="暖通/给排水/电气管线在走廊/管井区域应无交叉冲突",
        standard_ref="GB 50009-2012 §4.6",
        level="L3",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-024",
        category="coordination",
        major="arch",
        title="门窗洞与结构梁关系",
        description="门窗洞顶部不应位于结构梁下部，应预留过梁空间",
        standard_ref="GB 50009-2012 §3.4",
        level="L3",
        check_method="auto",
        func_id="DIST-001",
    ),
    ConstructionReviewItem(
        item_id="CD-025",
        category="coordination",
        major="arch",
        title="防火分区与疏散宽度协调",
        description="防火分区划分与疏散门/楼梯宽度应协调一致",
        standard_ref="GB 50016-2014 §5.5",
        level="L3",
        check_method="auto",
        func_id="DIM-006",
    ),
    ConstructionReviewItem(
        item_id="CD-026",
        category="coordination",
        major="arch",
        title="消防给水与电气联动",
        description="消防泵房/喷淋泵应标注启动控制方式，与电气图联动",
        standard_ref="GB 50974-2014 §5.1",
        level="L3",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-027",
        category="coordination",
        major="arch",
        title="无障碍与建筑布局协调",
        description="无障碍通道与建筑入口/卫生间/电梯布局协调",
        standard_ref="GB 50763-2012 §3.1",
        level="L3",
        check_method="auto",
        func_id="DIM-007",
    ),
    ConstructionReviewItem(
        item_id="CD-028",
        category="coordination",
        major="struct",
        title="基础与地质报告匹配",
        description="基础类型/埋深与地质勘察报告结论一致",
        standard_ref="GB 50007-2011 §3.1",
        level="L3",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-029",
        category="coordination",
        major="arch",
        title="图纸版本一致性",
        description="跨专业引用的图纸版本号应一致",
        standard_ref="GB/T 50100-2014 §6.2",
        level="L3",
        check_method="manual",
    ),
    ConstructionReviewItem(
        item_id="CD-030",
        category="coordination",
        major="arch",
        title="工程量汇总一致性",
        description="材料做法表/工程量汇总表与平面图数据一致",
        standard_ref="GB/T 50100-2014 §5.3",
        level="L3",
        check_method="manual",
    ),
]


def get_construction_review_items(
    major: Optional[str] = None,
    level: Optional[str] = None,
    category: Optional[str] = None,
    check_method: Optional[str] = None,
) -> List[Dict]:
    """按条件过滤返回施工图审查标准列表"""
    items = CONSTRUCTION_REVIEW_ITEMS
    if major:
        items = [i for i in items if i.major == major]
    if level:
        items = [i for i in items if i.level == level]
    if category:
        items = [i for i in items if i.category == category]
    if check_method:
        items = [i for i in items if i.check_method == check_method]
    return [
        {
            "item_id": i.item_id,
            "category": i.category,
            "major": i.major,
            "title": i.title,
            "description": i.description,
            "standard_ref": i.standard_ref,
            "level": i.level,
            "check_method": i.check_method,
            "func_id": i.func_id,
            "weight": i.weight,
        }
        for i in items
    ]
