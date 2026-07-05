#!/usr/bin/env python3
"""调试 _detect_floor_levels"""
import sys, os, re, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.baa_engine.drawing_parser import RawPrimitive
from src.baa_engine.semantic_analyzer import SemanticAnalyzer

# 创建测试数据
prims = [
    RawPrimitive("TEXT", "TEXT", "H001", {"x": 0, "y": 0, "width": 50, "height": 20}, {"text": "B1"}),
]

analyzer = SemanticAnalyzer()

# 直接手动复制方法逻辑
import math

all_x = []
all_y = []
for p in prims:
    bbox = p.bbox
    if bbox.get("width", 0) > 0:
        all_x.append(bbox["x"])
        all_x.append(bbox["x"] + bbox["width"])
    if bbox.get("height", 0) > 0:
        all_y.append(bbox["y"])
        all_y.append(bbox["y"] + bbox["height"])

print(f"all_x={all_x}")
print(f"all_y={all_y}")

drawing_width = max(all_x) - min(all_x) if all_x else 0
drawing_height = max(all_y) - min(all_y) if all_y else 0
print(f"drawing_width={drawing_width}, drawing_height={drawing_height}")

width_threshold = drawing_width * 0.8

# 1. 收集水平分隔线
separators = []
for p in prims:
    if p.dxf_type not in ("LINE", "LWPOLYLINE"):
        continue
    bbox = p.bbox
    bw = bbox.get("width", 0)
    bh = bbox.get("height", 0)
    center_y = bbox.get("y", 0) + bh / 2
    if bw > 0 and bh > 0 and bw / max(bh, 1) > 20:
        if bw >= width_threshold:
            separators.append({"y": center_y, "width": bw, "layer": p.layer})
print(f"separators={separators}")

# 2. 提取标高文字
elevation_texts = []
for p in prims:
    print(f"  processing: dxf_type={p.dxf_type}, text={p.properties.get('text', '')}")
    if p.dxf_type != "TEXT":
        print(f"    skip: not TEXT")
        continue
    text = p.properties.get("text", "").strip()
    if not text:
        print(f"    skip: empty text")
        continue
    bbox = p.bbox
    center_y = bbox.get("y", 0) + bbox.get("height", 0) / 2
    text_upper = text.upper()
    level = None
    label = text

    # "B1", "B2"
    import re
    m = re.match(r"^[Bb](\d+)$", text)
    print(f"    regex B match: {m}")
    if m:
        level = -int(m.group(1))
        label = f"B{m.group(1)}"

    print(f"    level={level}, label={label}")

    if level is not None:
        elevation_texts.append({
            "y": center_y,
            "level": level,
            "label": label,
            "text": text,
        })

print(f"elevation_texts={elevation_texts}")
print(f"len(elevation_texts)={len(elevation_texts)}")

# 3. 合并
floor_levels = []
sorted_seps = sorted(separators, key=lambda s: s["y"])
sorted_texts = sorted(elevation_texts, key=lambda t: t["y"])
print(f"sorted_seps={sorted_seps}, sorted_texts={sorted_texts}")

if not sorted_seps and not sorted_texts:
    print("returning early: no seps and no texts")
else:
    print("proceeding to floor generation")

# 无分隔线时，按标高文字聚类
if not sorted_seps and sorted_texts:
    print(f"text-only mode, len={len(sorted_texts)}")
    if len(sorted_texts) >= 1:
        clusters = []
        current_cluster = [sorted_texts[0]]
        for i in range(1, len(sorted_texts)):
            if abs(sorted_texts[i]["y"] - sorted_texts[i - 1]["y"]) < drawing_height * 0.1:
                current_cluster.append(sorted_texts[i])
            else:
                clusters.append(current_cluster)
                current_cluster = [sorted_texts[i]]
        if current_cluster:
            clusters.append(current_cluster)
        print(f"clusters={clusters}")

        cluster_centers = []
        for cluster in clusters:
            avg_y = sum(t["y"] for t in cluster) / len(cluster)
            cluster_centers.append({"y": avg_y, "label": cluster[0]["label"], "level": cluster[0]["level"]})
        cluster_centers.sort(key=lambda c: c["y"])
        print(f"cluster_centers={cluster_centers}")

        prev_y = min(all_y) if all_y else 0
        for i, cc in enumerate(cluster_centers):
            floor_levels.append({
                "level": i + 1,
                "label": cc["label"],
                "elevation": cc["level"],
                "y_range": [prev_y, cc["y"] + drawing_height * 0.05],
                "source": "text",
            })
            prev_y = cc["y"] + drawing_height * 0.05

print(f"floor_levels={floor_levels}")

# 最后调实际方法对比
print("\n--- Actual method call ---")
result = analyzer._detect_floor_levels(prims)
print(f"actual result: {result}")