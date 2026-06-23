"""
BAA 尺寸标注解析器
===================
从 DXF/DWG 图纸中提取 DIMENSION 实体，反推 door/window/staircase/corridor 等实体的实际尺寸。

设计原则：
1. 直接从 ezdwg/ezdxf 读取 DIMENSION 实体的 measurement 值
2. 根据 DIMENSION 的位置（text_midpoint/defpoint）匹配到附近的实体
3. 为匹配的实体注入准确的 width/height/area 属性

使用方式：
    parser = DimensionParser()
    dims = parser.extract_dimensions(file_path)
    # dims 是 [{handle, layer, measurement, text, position, ...}, ...]
    
    # 注入到实体：
    enriched = parser.inject_into_entities(dims, entities)
"""
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path


class DimensionParser:
    """尺寸标注解析器"""

    # 哪些实体类型需要从 DIMENSION 获取实际尺寸
    DIMENSIONABLE_TYPES = {"door", "window", "fire_door", "fire_window",
                           "corridor", "staircase", "fire_lane", "room",
                           "wall", "exit"}

    # 尺寸值单位的猜测（mm 还是 m）
    # 真实 DXF 中 DIMENSION 通常是 mm 单位
    # 合成 DXF 中可能是 mm 或 m

    def extract_dimensions(self, file_path: str) -> List[Dict]:
        """从图纸中提取 DIMENSION 实体"""
        ext = Path(file_path).suffix.lower()
        dimensions = []

        if ext == ".dwg":
            # DWG：直接用 ezdwg 读 DIMENSION 的 dxf 字典
            try:
                import ezdwg
                dwg_doc = ezdwg.read(file_path)
                msp = dwg_doc.modelspace()
                try:
                    dim_ents = list(msp.query(types="DIMENSION"))
                except Exception:
                    try:
                        dim_ents = list(msp.query(types=['DIMENSION']))
                    except Exception:
                        dim_ents = []
                for ent in dim_ents:
                    try:
                        d = ent.dxf
                        # ezdwg 的 measurement 字段名为 actual_measurement
                        meas = d.get("actual_measurement", d.get("measurement", None))
                        if meas is None or meas <= 0.1:
                            continue
                        defp2 = d.get("defpoint2", (0, 0, 0))
                        defp3 = d.get("defpoint3", (0, 0, 0))
                        text_mid = d.get("text_midpoint", (0, 0, 0))
                        dimensions.append({
                            "handle": d.get("handle", ""),
                            "layer": d.get("layer", "0"),
                            "measurement": float(meas),
                            "text": d.get("text", ""),
                            "dimtype": d.get("dimtype", 0),
                            "defpoint2": {"x": defp2[0], "y": defp2[1]},
                            "defpoint3": {"x": defp3[0], "y": defp3[1]},
                            "text_midpoint": {"x": text_mid[0], "y": text_mid[1]},
                        })
                    except Exception:
                        continue
            except Exception as e:
                pass
        else:
            # DXF：用 ezdxf 读
            try:
                import ezdxf
                doc = ezdxf.readfile(file_path)
                msp = doc.modelspace()
                for entity in msp:
                    if entity.dxftype() != "DIMENSION":
                        continue
                    try:
                        meas = entity.get_measurement()
                        if meas is None or meas <= 0.1:
                            continue
                        dimensions.append({
                            "handle": entity.dxf.handle if hasattr(entity.dxf, 'handle') else '',
                            "layer": entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0',
                            "measurement": float(meas),
                            "text": entity.get_measurement_text() if hasattr(entity, 'get_measurement_text') else str(meas),
                            "dimtype": str(entity.dxf.dimtype) if hasattr(entity.dxf, 'dimtype') else 'LINEAR',
                            "defpoint2": {"x": entity.dxf.defpoint2.x if hasattr(entity.dxf.defpoint2, 'x') else 0,
                                          "y": entity.dxf.defpoint2.y if hasattr(entity.dxf.defpoint2, 'y') else 0},
                            "defpoint3": {"x": entity.dxf.defpoint3.x if hasattr(entity.dxf.defpoint3, 'x') else 0,
                                          "y": entity.dxf.defpoint3.y if hasattr(entity.dxf.defpoint3, 'y') else 0},
                            "text_midpoint": {"x": entity.dxf.text_midpoint.x if hasattr(entity.dxf, 'text_midpoint') and hasattr(entity.dxf.text_midpoint, 'x') else 0,
                                              "y": entity.dxf.text_midpoint.y if hasattr(entity.dxf, 'text_midpoint') and hasattr(entity.dxf.text_midpoint, 'y') else 0},
                        })
                    except Exception:
                        continue
            except Exception:
                pass

        return dimensions

    def classify_dimensions(self, dimensions: List[Dict]) -> Dict[str, List[Dict]]:
        """按用途分类尺寸标注

        返回:
            {"width": [...], "height": [...], "length": [...], "other": [...]}
        """
        classified = {"width": [], "height": [], "length": [], "other": []}

        for dim in dimensions:
            meas = dim.get("measurement", 0)
            dp2 = dim.get("defpoint2", {})
            dp3 = dim.get("defpoint3", {})
            text = dim.get("text", "")

            # 计算方向向量
            dx = abs(dp3.get("x", 0) - dp2.get("x", 0))
            dy = abs(dp3.get("y", 0) - dp2.get("y", 0))

            # 水平 → width/长度，垂直 → height
            if dx > dy * 2:
                classified["width"].append(dim)
            elif dy > dx * 2:
                classified["height"].append(dim)
            else:
                classified["length"].append(dim)

        return classified

    def match_to_entities(self, dimensions: List[Dict],
                          entities: List[Dict],
                          max_distance: float = 5.0) -> List[Dict]:
        """将 DIMENSION 匹配到附近的实体

        策略：
        - DIMENSION 的 text_midpoint 离实体 bbox 中心最近 → 匹配
        - 一个实体可能被多个 DIMENSION 标注（宽度+高度）
        - 一个 DIMENSION 只能匹配到一个实体

        返回:
            增强后的 entities 列表（注入 measurement 属性）
        """
        if not entities or not dimensions:
            return entities

        # 计算每个实体的中心
        entity_centers = []
        for i, e in enumerate(entities):
            bbox = e.get("bbox", {})
            cx = bbox.get("x", 0) + bbox.get("width", 0) / 2
            cy = bbox.get("y", 0) + bbox.get("height", 0) / 2
            entity_centers.append((i, cx, cy))

        # 对每个 DIMENSION，找最近的实体
        matched_dims = set()
        for dim in dimensions:
            tmid = dim.get("text_midpoint", {})
            dmx, dmy = tmid.get("x", 0), tmid.get("y", 0)

            best_dist = float("inf")
            best_idx = None

            for i, ecx, ecy in entity_centers:
                dist = ((dmx - ecx) ** 2 + (dmy - ecy) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_idx = i

            if best_idx is not None and best_dist < max_distance:
                # 注入属性
                etype = entities[best_idx].get("type", "")
                meas = dim.get("measurement", 0)

                if "properties" not in entities[best_idx]:
                    entities[best_idx]["properties"] = {}

                props = entities[best_idx]["properties"]

                # 根据 DIMENSION 方向决定注入什么属性
                dp2 = dim.get("defpoint2", {})
                dp3 = dim.get("defpoint3", {})
                dx = abs(dp3.get("x", 0) - dp2.get("x", 0))
                dy = abs(dp3.get("y", 0) - dp2.get("y", 0))

                # 真实图纸单位是 mm，转为 m
                # 如果测量值 > 100，视为 mm
                meas_m = meas / 1000.0 if meas > 100 else meas

                if dx > dy * 2:  # 水平尺寸 → width
                    if "width" not in props or props.get("detection_source") != "yolo":
                        props["width"] = meas_m
                        props["clear_width"] = meas_m
                        props["_dimension_source"] = "dimension"
                elif dy > dx * 2:  # 垂直尺寸 → height
                    if "height" not in props:
                        props["height"] = meas_m
                        props["_dimension_source"] = "dimension"
                else:
                    # 斜向 → 作为长度
                    props["length"] = meas_m
                    props["_dimension_source"] = "dimension"

                matched_dims.add(id(dim))

        return entities

    def inject_into_entities(self, dimensions: List[Dict],
                              entities: List[Dict]) -> List[Dict]:
        """提取 + 分类 + 匹配 + 注入 一键完成"""
        classified = self.classify_dimensions(dimensions)
        all_dims = classified["width"] + classified["height"] + classified["length"]
        return self.match_to_entities(all_dims, entities)
