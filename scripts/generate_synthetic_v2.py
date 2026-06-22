#!/usr/bin/env python3
"""
BAA 合成图纸生成器 V2.1
================================
V2基础上改进：
1. 修正语义分析器无法识别合成图纸实体的问题
2. 在图纸中嵌入结构化实体元数据，让语义分析器能正确归并
3. 改进bbox计算（ezdxf的LWPOLYLINE/POLYLINE/LINE手动算）
"""
import ezdxf
from ezdxf.math import Vec2
from pathlib import Path
import random
import json
import os
import sys
import math

# 项目根目录
ROOT = Path(os.path.dirname(__file__)) / ".."
sys.path.insert(0, str(ROOT / "src"))

OUTPUT_DIR = ROOT / "data" / "drawings" / "synthetic_v2"
MANIFEST_FILE = OUTPUT_DIR / "manifest.json"

# 建筑类型配置
BUILDING_TYPES = ["civil", "industrial"]
BUILDING_VARIANTS = {
    "civil": ["office", "residential", "school", "shopping_mall"],
    "industrial": ["factory", "warehouse", "power_plant", "data_center"],
}

BUILDING_SIZES = {
    "civil": {
        "office":          {"w": (20, 50),  "h": (15, 40)},
        "residential":     {"w": (15, 35),  "h": (10, 25)},
        "school":          {"w": (30, 60),  "h": (20, 45)},
        "shopping_mall":   {"w": (40, 80),  "h": (30, 60)},
    },
    "industrial": {
        "factory":         {"w": (30, 80),  "h": (20, 60)},
        "warehouse":       {"w": (40, 100), "h": (30, 70)},
        "power_plant":     {"w": (50, 120), "h": (30, 80)},
        "data_center":     {"w": (30, 70),  "h": (25, 50)},
    },
}


# ── 辅助函数 ──────────────────────────────────────────────

def bbox_of_line(x1, y1, x2, y2):
    """手动计算LINE的bbox"""
    return {
        "x": min(x1, x2), "y": min(y1, y2),
        "width": abs(x2 - x1), "height": abs(y2 - y1),
    }


def bbox_of_polyline(points):
    """手动计算多边形bbox"""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return {
        "x": min(xs), "y": min(ys),
        "width": max(xs) - min(xs), "height": max(ys) - min(ys),
    }


def bbox_center(b):
    return (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)


# ── 违规注入 ──────────────────────────────────────────────

def decide_violations(building_type, variant):
    all_func_ids = [
        "DIM-001", "DIM-002", "DIM-003", "DIST-001", "COUNT-001",
        "ATTR-001", "DIM-004", "AREA-001", "EXIST-001", "DIM-005",
        "DIM-006", "DIM-007", "EXIST-002", "EXIST-003", "EXIST-004",
        "EXIST-005", "EXIST-006", "ATTR-002", "LIGHT-001",
    ]
    if building_type == "industrial":
        unavailable = {"DIM-006", "AREA-001", "EXIST-003", "EXIST-005"}
    else:
        unavailable = set()
    available = [f for f in all_func_ids if f not in unavailable]
    random.shuffle(available)
    n = random.randint(2, 4)
    violated = set(available[:n])
    result = {}
    for fid in all_func_ids:
        if fid in violated:
            result[fid] = {"fail": True, "severity": random.choice(["major", "critical"])}
        else:
            result[fid] = {"fail": False}
    return result


# ── 生成器 ────────────────────────────────────────────────

def generate_drawing(building_type, variant, dwg_id, violations):
    sizes = BUILDING_SIZES[building_type][variant]
    w = round(random.uniform(*sizes["w"]), 1)
    h = round(random.uniform(*sizes["h"]), 1)

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # 存储结构化实体，用于输出到META层
    structured_entities = []

    def register_entity(etype, x, y, w_, h_, props=None, bbox=None):
        """注册一个结构化实体，写入META图层"""
        nonlocal structured_entities
        ent = {
            "type": etype,
            "bbox": bbox or {"x": x, "y": y, "width": w_, "height": h_},
            "properties": props or {},
        }
        structured_entities.append(ent)
        return ent

    # ── 绘制 ──────────────────────────────────────────

    # 外墙
    add_rectangle(msp, 0, 0, w, h, "WALL")
    wall_bbox = {"x": 0, "y": 0, "width": w, "height": h}
    register_entity("wall", 0, 0, w, h, {"area": w * h}, bbox=wall_bbox)

    # 走廊
    corridor_w = 2.0
    cx = w * 0.5 - corridor_w * 0.5
    add_wall(msp, cx, 0, cx, h, "WALL")
    add_wall(msp, cx + corridor_w, 0, cx + corridor_w, h, "WALL")

    if violations.get("DIM-004", {}).get("fail"):
        corridor_actual = 0.8
    else:
        corridor_actual = 1.4

    cbbox = {"x": cx, "y": 0, "width": corridor_actual, "height": h}
    register_entity("corridor", cx, 0, corridor_actual, h,
                    {"clear_width": corridor_actual, "width": corridor_actual}, bbox=cbbox)

    # 房间
    room_width = cx - 0.5
    room_count = max(2, int(h / 4))
    room_h = h / room_count

    for i in range(room_count):
        ry = i * room_h + 0.5
        # 左侧房间
        add_rectangle(msp, 0.5, ry, room_width, room_h - 0.5, "ROOM")
        rbbox = {"x": 0.5, "y": ry, "width": room_width, "height": room_h - 0.5}
        register_entity("room", 0.5, ry, room_width, room_h - 0.5,
                        {"area": room_width * (room_h - 0.5)}, bbox=rbbox)

        # 门
        door_x = room_width
        door_y = ry + room_h * 0.3
        door_w = 0.9
        add_door(msp, door_x, door_y, door_w, "DOOR")
        db = {"x": door_x, "y": door_y, "width": 0.05, "height": door_w}
        register_entity("door", door_x, door_y, 0.05, door_w, {"width": door_w}, bbox=db)

        # 部分防火门
        if random.random() > 0.6:
            add_door(msp, door_x + 0.1, door_y + 1.0, 1.0, "FIRE_DOOR",
                     fire_rating=1, fire_rating_label="甲")
            fdb = {"x": door_x + 0.1, "y": door_y + 1.0, "width": 0.05, "height": 1.0}
            register_entity("fire_door", door_x + 0.1, door_y + 1.0, 0.05, 1.0,
                            {"fire_rating": 1, "rating": 1, "width": 1.0}, bbox=fdb)

        # 窗
        win_w = room_width * 0.6
        add_window(msp, 0.5, ry + 0.1, win_w, "WINDOW")
        wbbox = {"x": 0.5, "y": ry + 0.1, "width": win_w, "height": 0.05}
        register_entity("window", 0.5, ry + 0.1, win_w, 0.05,
                        {"width": win_w, "area": win_w * 0.05}, bbox=wbbox)

        # 右侧房间
        rx = cx + corridor_w + 0.5
        rw2 = w - rx - 0.5
        add_rectangle(msp, rx, ry, rw2, room_h - 0.5, "ROOM")
        rbbox2 = {"x": rx, "y": ry, "width": rw2, "height": room_h - 0.5}
        register_entity("room", rx, ry, rw2, room_h - 0.5,
                        {"area": rw2 * (room_h - 0.5)}, bbox=rbbox2)

    # 楼梯
    stair_w = 2.5
    stair_h_val = 6.0
    stair_clear_w = 1.5
    if violations.get("DIM-001", {}).get("fail"):
        stair_clear_w = 0.9

    add_staircase(msp, 0.5, h - stair_h_val - 0.5, stair_w, stair_h_val, "STAIR")
    sbbox = {"x": 0.5, "y": h - stair_h_val - 0.5, "width": stair_w, "height": stair_h_val}
    register_entity("staircase", 0.5, h - stair_h_val - 0.5, stair_w, stair_h_val,
                    {"clear_width": stair_clear_w, "width": stair_clear_w}, bbox=sbbox)

    if not violations.get("EXIST-001", {}).get("fail"):
        add_staircase(msp, w - stair_w - 0.5, h - stair_h_val - 0.5,
                      stair_w, stair_h_val, "STAIR")
        sbbox2 = {"x": w - stair_w - 0.5, "y": h - stair_h_val - 0.5,
                  "width": stair_w, "height": stair_h_val}
        register_entity("staircase", w - stair_w - 0.5, h - stair_h_val - 0.5,
                        stair_w, stair_h_val,
                        {"clear_width": 1.5, "width": 1.5, "exists": True}, bbox=sbbox2)
        add_door(msp, cx + corridor_w, h - stair_h_val - 0.5 + stair_h_val * 0.3,
                 1.0, "FIRE_DOOR", fire_rating=1, fire_rating_label="甲")
        fdb2 = {"x": cx + corridor_w, "y": h - stair_h_val - 0.5 + stair_h_val * 0.3,
                "width": 0.05, "height": 1.0}
        register_entity("fire_door", cx + corridor_w, h - stair_h_val - 0.5 + stair_h_val * 0.3,
                        0.05, 1.0, {"fire_rating": 1, "rating": 1, "width": 1.0}, bbox=fdb2)

    # 安全出口
    exit_count = 2
    if violations.get("COUNT-001", {}).get("fail"):
        exit_count = 1

    if exit_count >= 1:
        add_exit_sign(msp, 1, 1, "EXIT")
        add_door(msp, 0.5, 0.5, 1.0, "EXIT")
        register_entity("exit", 0.5, 0.5, 1.0, 0.5,
                        {"count": 1, "exists": True, "exit_count": 1},
                        bbox={"x": 0.5, "y": 0.5, "width": 1.0, "height": 0.5})
    if exit_count >= 2:
        add_exit_sign(msp, w - 2, 1, "EXIT")
        add_door(msp, w - 1.5, 0.5, 1.0, "EXIT")
        register_entity("exit", w - 1.5, 0.5, 1.0, 0.5,
                        {"count": 1, "exists": True, "exit_count": 1},
                        bbox={"x": w - 1.5, "y": 0.5, "width": 1.0, "height": 0.5})

    # 消防车道
    add_fire_lane(msp, -2, -2, w + 4, "FIRE_LANE")
    fl_w = 4.5
    if violations.get("DIM-003", {}).get("fail"):
        fl_w = 3.0
    register_entity("fire_lane", -2, -2, w + 4, 0.5,
                    {"width": fl_w}, bbox={"x": -2, "y": -2, "width": w + 4, "height": 0.5})

    # 防火分区
    area = w * h
    register_entity("fire_zone", 0, 0, w, h,
                    {"area": area}, bbox={"x": 0, "y": 0, "width": w, "height": h})

    # 消防窗
    fw_size = 1.2
    if violations.get("DIM-005", {}).get("fail"):
        fw_size = 0.5
    add_window(msp, w * 0.3, h - 0.3, fw_size, "FIRE_WINDOW")
    register_entity("fire_window", w * 0.3, h - 0.3, fw_size, 0.05,
                    {"width": fw_size, "net_area": fw_size * 0.3, "area": fw_size * 0.3},
                    bbox={"x": w * 0.3, "y": h - 0.3, "width": fw_size, "height": 0.05})

    # 疏散指示
    if not violations.get("EXIST-004", {}).get("fail"):
        add_exit_sign(msp, cx + 0.3, h * 0.5, "EXIT")
        register_entity("exit_sign", cx + 0.3, h * 0.5, 0.5, 0.5,
                        {"exists": True, "count": 1},
                        bbox={"x": cx + 0.3, "y": h * 0.5, "width": 0.5, "height": 0.5})

    # 自动灭火
    if building_type == "civil" and not violations.get("EXIST-005", {}).get("fail"):
        msp.add_text("自动喷淋系统已设置", height=0.3, dxfattribs={
            "layer": "FIRE_SYSTEM", "insert": (w * 0.5, h + 0.5)})
        register_entity("sprinkler_system", w * 0.5, h + 0.5, 5, 0.5,
                        {"exists": True}, bbox={"x": w * 0.5, "y": h + 0.5, "width": 5, "height": 0.5})

    # 火灾报警
    if not violations.get("EXIST-006", {}).get("fail"):
        msp.add_text("火灾自动报警系统已设置", height=0.3, dxfattribs={
            "layer": "FIRE_SYSTEM", "insert": (w * 0.5, h + 1.0)})
        register_entity("fire_alarm", w * 0.5, h + 1.0, 5, 0.5,
                        {"exists": True}, bbox={"x": w * 0.5, "y": h + 1.0, "width": 5, "height": 0.5})

    # 应急照明
    if not violations.get("LIGHT-001", {}).get("fail"):
        msp.add_text("应急照明1.5lx", height=0.3, dxfattribs={
            "layer": "LIGHT", "insert": (cx, h * 0.3)})
        register_entity("evacuation_lighting", cx, h * 0.3, 3, 0.5,
                        {"illuminance": 1.5, "lux": 1.5},
                        bbox={"x": cx, "y": h * 0.3, "width": 3, "height": 0.5})

    # 管道井封堵
    if not violations.get("EXIST-002", {}).get("fail"):
        add_rectangle(msp, w * 0.8, h * 0.2, 1.0, 1.0, "SHAFT_SEALED")
        msp.add_text("管道井已封堵", height=0.3, dxfattribs={
            "layer": "SHAFT_SEALED", "insert": (w * 0.8, h * 0.15)})
        register_entity("shaft", w * 0.8, h * 0.2, 1.0, 1.0,
                        {"sealed": True, "exists": True, "hole_sealed": True},
                        bbox={"x": w * 0.8, "y": h * 0.2, "width": 1.0, "height": 1.0})

    # 保温材料
    if not violations.get("ATTR-002", {}).get("fail"):
        msp.add_text("保温材料:A级", height=0.3, dxfattribs={
            "layer": "INSULATION", "insert": (0.5, h + 1.5)})
        register_entity("insulation", 0.5, h + 1.5, 3, 0.5,
                        {"fire_rating": 3, "rating": 3},
                        bbox={"x": 0.5, "y": h + 1.5, "width": 3, "height": 0.5})

    # 疏散距离标注
    travel_dist = 20.0
    if violations.get("DIST-001", {}).get("fail"):
        travel_dist = 35.0
    msp.add_text(f"疏散距离:{travel_dist}m", height=0.3, dxfattribs={
        "layer": "DIM", "insert": (0.5, h - 0.5)})
    register_entity("room", 0, 0, w, h,
                    {"travel_distance": travel_dist},
                    bbox={"x": 0, "y": 0, "width": w, "height": h})

    # 避难层 (民用)
    if building_type == "civil":
        refuge_area = 6.0
        if violations.get("AREA-001", {}).get("fail"):
            refuge_area = 3.0
        msp.add_text(f"避难层净面积:{refuge_area}㎡/人", height=0.3, dxfattribs={
            "layer": "DIM", "insert": (w * 0.6, h + 0.5)})
        register_entity("refuge_floor", w * 0.6, h + 0.5, 5, 0.5,
                        {"area_per_person": refuge_area, "area": refuge_area},
                        bbox={"x": w * 0.6, "y": h + 0.5, "width": 5, "height": 0.5})

    # ── 写入结构化实体元数据（META图层，供语义分析器读取） ──
    y_offset = -2.0
    for se in structured_entities:
        etype = se["type"]
        eb = se["bbox"]
        props = se["properties"]
        line = f"ENTITY:{etype}|x:{eb['x']:.2f}|y:{eb['y']:.2f}|w:{eb['width']:.2f}|h:{eb['height']:.2f}"
        for k, v in props.items():
            line += f"|{k}:{v}"
        msp.add_text(line, height=0.2, dxfattribs={
            "layer": "META", "insert": (0, y_offset)})
        y_offset -= 0.3

    # ── 保存 ──
    filename = f"drawing_{dwg_id:04d}.dxf"
    filepath = OUTPUT_DIR / filename
    doc.saveas(str(filepath))

    return {
        "file_id": f"synthetic_v2_{dwg_id:04d}",
        "filename": filename,
        "building_type": building_type,
        "variant": variant,
        "width_m": w,
        "height_m": h,
        "area_m2": round(w * h, 1),
        "violations": violations,
        "violation_count": sum(1 for v in violations.values() if v["fail"]),
        "entity_count": len(structured_entities),
    }


# ── 图元绘制辅助（同V2） ──────────────────────────────

def add_wall(msp, x1, y1, x2, y2, layer="WALL", thickness=None):
    attribs = {"layer": layer}
    if thickness:
        attribs["thickness"] = thickness
    msp.add_line((x1, y1), (x2, y2), dxfattribs=attribs)

def add_rectangle(msp, x, y, w, h, layer="WALL"):
    pts = [(x, y), (x+w, y), (x+w, y+h), (x, y+h), (x, y)]
    msp.add_lwpolyline(pts, dxfattribs={"layer": layer})

def add_staircase(msp, x, y, w, h, layer="STAIR"):
    msp.add_lwpolyline([
        (x, y), (x+w, y), (x+w, y+h), (x, y+h), (x, y)
    ], dxfattribs={"layer": layer})
    steps = int(h / 0.3)
    for i in range(1, steps):
        sy = y + i * 0.3
        msp.add_line((x, sy), (x+w, sy), dxfattribs={"layer": layer})

def add_door(msp, x, y, w, layer="DOOR", fire_rating=0, fire_rating_label=None):
    msp.add_line((x, y), (x, y + w), dxfattribs={"layer": layer})
    msp.add_arc((x, y), w, 0, 90, dxfattribs={"layer": layer})
    if fire_rating > 0:
        label = fire_rating_label or "甲"
        msp.add_text(label, height=0.3, dxfattribs={
            "layer": "FIRE_DOOR", "insert": (x + 0.2, y + 0.2)})

def add_window(msp, x, y, w, layer="WINDOW"):
    msp.add_line((x, y), (x + w, y), dxfattribs={"layer": layer})
    msp.add_line((x, y + 0.05), (x + w, y + 0.05), dxfattribs={"layer": layer})

def add_exit_sign(msp, x, y, layer="EXIT"):
    msp.add_text("→", height=0.4, dxfattribs={"layer": layer, "insert": (x, y)})

def add_fire_lane(msp, x, y, w, layer="FIRE_LANE"):
    msp.add_line((x, y), (x + w, y), dxfattribs={"layer": layer})
    msp.add_line((x, y + 0.5), (x + w, y + 0.5), dxfattribs={"layer": layer})
    msp.add_text("消防车道", height=0.3, dxfattribs={
        "layer": layer, "insert": (x + 1, y - 0.8)})


# ── 主流程 ────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total_per_variant = 25

    manifest = []
    dwg_id = 1

    # 先清除旧文件
    for f in OUTPUT_DIR.glob("*.dxf"):
        f.unlink()

    print(f"🚀 BAA 合成图纸生成器 V2.1")
    print(f"   输出目录: {OUTPUT_DIR}")
    print(f"   每种变体: {total_per_variant} 张")
    print()

    for bt in BUILDING_TYPES:
        for variant in BUILDING_VARIANTS[bt]:
            print(f"  [{bt}/{variant}] 生成 {total_per_variant} 张...")
            for i in range(total_per_variant):
                violations = decide_violations(bt, variant)
                entry = generate_drawing(bt, variant, dwg_id, violations)
                manifest.append(entry)
                dwg_id += 1
            print(f"    ✅ {total_per_variant} 张完成")

    summary = {
        "total": len(manifest),
        "building_types": BUILDING_TYPES,
        "variants": BUILDING_VARIANTS,
        "per_variant": total_per_variant,
    }
    manifest_data = {"summary": summary, "drawings": manifest}

    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, ensure_ascii=False, indent=2)

    total_violations = sum(e["violation_count"] for e in manifest)
    print()
    print(f"✅ 完成！总计: {len(manifest)} 张合成图纸")
    print(f"   总违规数: {total_violations}")
    print(f"   平均违规/张: {total_violations / len(manifest):.1f}")
    print(f"   清单: {MANIFEST_FILE}")


if __name__ == "__main__":
    main()