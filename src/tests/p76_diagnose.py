"""P76 诊断：6 张黄金标准图纸逐项分析"""

import sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from baa_engine.drawing_parser import DrawingParser
from baa_engine.semantic_analyzer import SemanticAnalyzer

parser = DrawingParser()
analyzer = SemanticAnalyzer()

data_dir = os.path.join(os.path.dirname(__file__), "..", "data")

targets = [
    ("20210409-3#泵房_t3.dxf", ["EVAC-004"]),
    ("202109409-2#配电房_t3.dxf", ["EVAC-004"]),
    ("A1云计算中心平面图0405_t3.dxf", ["DIST-001", "EVAC-001", "EVAC-004"]),
    ("ZY项目1#数据中心机房平立剖面图_t7_t3.dxf", ["EVAC-001"]),
    ("东莞通-建筑-外部参照（不打印）.dxf", ["DIST-001", "EVAC-001"]),
    ("A1云计算中心_水消防2017.03.31_t3.dxf", ["DIM-006"]),
]

for fname, expected_funcs in targets:
    path = os.path.join(data_dir, fname)
    print(f"\n{'='*70}")
    print(f"📄 {fname} → 目标: {expected_funcs}")
    print(f"{'='*70}")

    if not os.path.exists(path):
        print("   ❌ 文件不存在")
        continue

    result = parser.parse(path, fname, detect_sheets=False)
    if not result.success:
        print(f"   ❌ 解析失败: {result.error}")
        continue

    out = analyzer.analyze(result.primitives, result.dimensions, building_type="civil")
    ents = out.get("entities", [])

    # 统计实体类型
    types = {}
    for e in ents:
        t = e.get("type", "unknown")
        types[t] = types.get(t, 0) + 1

    # 关键类型
    key_types = [
        "room",
        "corridor",
        "door",
        "exit_door",
        "pump_room",
        "stair",
        "fire_door",
        "fire_wall",
        "rescue_window",
    ]
    present = {k: types.get(k, 0) for k in key_types if types.get(k, 0) > 0}
    missing = [k for k in key_types if k not in present]
    print(f"   实体类型（关键）: {json.dumps(present, ensure_ascii=False)}")
    print(f"   缺失类型: {missing}")

    # 1. EVAC 分析是否执行
    rooms = [e for e in ents if e.get("type") in ("room", "corridor", "pump_room", "lobby")]
    evac_ents = [e for e in ents if any("evac" in k for k in e)]
    print(f"\n   [EVAC]")
    print(f"   room/corridor/pump_room/lobby: {len(rooms)}")
    print(f"   带 evacuation 属性的实体: {len(evac_ents)}")

    if evac_ents:
        for e in evac_ents[:5]:
            attrs = {k: v for k, v in e.items() if "evac" in k.lower()}
            print(f"     {e.get('id')} ({e.get('type')}): {json.dumps(attrs)}")

    # 2. 各期望函数检查
    print(f"\n   [期望函数]")
    for fid in expected_funcs:
        print(f"   --- {fid} ---")
        if fid == "EVAC-004":
            # 需要 evacuation_connected 属性
            conn_ents = [
                e
                for e in ents
                if e.get("evacuation_connected") is not None or "evacuation_bottleneck" in e
            ]
            print(f"   evacuation_connected 实体: {len(conn_ents)}")
            if len(conn_ents) == 0:
                print(f"   ❌ 漏检根因: 无实体带 evacuation_connected 属性")
                print(f"      前置条件: verify_evacuation_connectivity() 返回空")
                print(f"      原因: room/corridor 实体数={len(rooms)}，BFS 拓扑未建立")
        elif fid == "EVAC-001":
            route_ents = [e for e in ents if "has_evacuation_route" in e]
            print(f"   has_evacuation_route 实体: {len(route_ents)}")
            if len(route_ents) == 0:
                print(f"   ❌ 漏检根因: 无实体带 has_evacuation_route 属性")
                print(f"      前置条件: analyze_evacuation_routes() 返回空")
        elif fid == "DIST-001":
            # 需要 travel_distance 属性
            td_ents = [
                e
                for e in ents
                if "travel_distance" in e or e.get("properties", {}).get("travel_distance")
            ]
            print(f"   travel_distance 实体: {len(td_ents)}")
            if len(td_ents) == 0:
                print(f"   ❌ 漏检根因: 无实体带 travel_distance 属性")
                print(f"      前置条件: EVAC 路径分析未产出 travel_distance")
        elif fid == "DIM-006":
            doors = [e for e in ents if e.get("type") in ("door", "exit_door")]
            print(f"   door/exit_door: {len(doors)}")
            if len(doors) == 0:
                print(f"   ❌ 漏检根因: 无 door/exit_door 实体")
                print(f"      原因: 水消防图以 pipe/wall/text 为主，门实体未被识别")

print(f"\n{'='*70}")
print("诊断完成")
print(f"{'='*70}")
