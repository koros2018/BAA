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
        """将 DIMENSION 匹配到附近的实体（V2增强版）

        策略（V2）：
        - 距离约束：DIMENSION 的 text_midpoint 离实体 bbox 最近
        - 方向约束：水平 DIM → width，垂直 DIM → height
        - 投影约束：DIM 的 defpoint2/defpoint3 必须落在实体 bbox 的投影范围内
          （解决跨多个实体的大尺寸标注被误匹配到远处实体的问题）
        - 单位转换优化：使用 min(测量值, 测量值/1000) 双重检查
          （解决 m/mm 单位混淆导致的走廊宽度 1.096m 误报问题）

        返回:
            增强后的 entities 列表（注入 measurement 属性）
        """
        import math
        
        if not entities or not dimensions:
            return entities

        # 预处理：计算每个实体的中心和边界
        entity_info = []
        for i, e in enumerate(entities):
            bbox = e.get("bbox", {})
            cx = bbox.get("x", 0) + bbox.get("width", 0) / 2
            cy = bbox.get("y", 0) + bbox.get("height", 0) / 2
            x1 = bbox.get("x", 0)
            y1 = bbox.get("y", 0)
            x2 = x1 + bbox.get("width", 0)
            y2 = y1 + bbox.get("height", 0)
            entity_info.append({
                "idx": i,
                "cx": cx, "cy": cy,
                "x1": x1, "y1": y1,
                "x2": x2, "y2": y2,
            })

        matched_dims = set()
        
        # 对每个 DIMENSION，先用距离找候选，再用方向+投影约束筛选
        for dim in dimensions:
            tmid = dim.get("text_midpoint", {})
            dmx, dmy = tmid.get("x", 0), tmid.get("y", 0)
            dp2 = dim.get("defpoint2", {})
            dp3 = dim.get("defpoint3", {})
            
            # 计算标注方向向量
            dx_vec = abs(dp3.get("x", 0) - dp2.get("x", 0))
            dy_vec = abs(dp3.get("y", 0) - dp2.get("y", 0))
            is_horizontal = dx_vec > dy_vec * 2
            is_vertical = dy_vec > dx_vec * 2
            
            # 标注的两个端点坐标
            d2x, d2y = dp2.get("x", 0), dp2.get("y", 0)
            d3x, d3y = dp3.get("x", 0), dp3.get("y", 0)
            # defpoint 最小/最大
            dp_xmin, dp_xmax = min(d2x, d3x), max(d2x, d3x)
            dp_ymin, dp_ymax = min(d2y, d3y), max(d2y, d3y)

            best_dist = float("inf")
            best_idx = None
            best_projection = -1.0  # 投影重叠度

            for info in entity_info:
                # 距离筛选：text_midpoint 到实体中心
                dist = ((dmx - info["cx"]) ** 2 + (dmy - info["cy"]) ** 2) ** 0.5
                if dist > max_distance * 2000:  # 放宽初始阈值
                    continue
                
                # 投影约束：DIM 的 defpoint 投影必须在实体 bbox 范围内
                if is_horizontal:
                    # 水平标注：y 方向投影重叠
                    proj_overlap = max(0, min(info["y2"], dp_ymax) - max(info["y1"], dp_ymin))
                    ent_h = info["y2"] - info["y1"]
                    if ent_h > 0:
                        proj_ratio = proj_overlap / ent_h
                    else:
                        proj_ratio = 0
                    # x 方向端点必须在实体投影范围内
                    x_overlap = max(0, min(info["x2"], dp_xmax) - max(info["x1"], dp_xmin))
                elif is_vertical:
                    # 垂直标注：x 方向投影重叠
                    proj_overlap = max(0, min(info["x2"], dp_xmax) - max(info["x1"], dp_xmin))
                    ent_w = info["x2"] - info["x1"]
                    if ent_w > 0:
                        proj_ratio = proj_overlap / ent_w
                    else:
                        proj_ratio = 0
                    y_overlap = max(0, min(info["y2"], dp_ymax) - max(info["y1"], dp_ymin))
                else:
                    # 斜向标注：用整体 IoU
                    proj_overlap = 0
                    proj_ratio = 0
                
                # 组合评分：距离 + 投影重叠
                score = dist * (1.5 - min(proj_ratio, 1.0))
                
                if score < best_dist or (abs(score - best_dist) < 1 and proj_ratio > best_projection):
                    best_dist = score
                    best_idx = info["idx"]
                    best_projection = proj_ratio

            if best_idx is not None:
                meas = dim.get("measurement", 0)

                if "properties" not in entities[best_idx]:
                    entities[best_idx]["properties"] = {}

                props = entities[best_idx]["properties"]

                # 单位转换优化（V2）：
                # 用 min(原始值, 原始值/1000) 双重检查
                # 如果原始值>100且除以1000后更合理（0.3~30m），取除以1000
                if meas > 100 and 0.3 < meas / 1000 < 30:
                    meas_m = meas / 1000.0
                elif meas > 10000 and 0.3 < meas / 1000 < 30:
                    meas_m = meas / 1000.0
                else:
                    meas_m = meas
                
                # 根据方向注入
                if is_horizontal:
                    if "width" not in props or props.get("detection_source") != "yolo":
                        props["width"] = meas_m
                        props["clear_width"] = meas_m
                        props["_dimension_source"] = "dimension"
                        props["_dimension_raw"] = meas
                elif is_vertical:
                    if "height" not in props:
                        props["height"] = meas_m
                        props["_dimension_source"] = "dimension"
                        props["_dimension_raw"] = meas
                else:
                    props["length"] = meas_m
                    props["_dimension_source"] = "dimension"
                    props["_dimension_raw"] = meas

                matched_dims.add(id(dim))

        return entities

    def inject_into_entities(self, dimensions: List[Dict],
                              entities: List[Dict]) -> List[Dict]:
        """提取 + 分类 + 匹配 + 注入 一键完成"""
        classified = self.classify_dimensions(dimensions)
        all_dims = classified["width"] + classified["height"] + classified["length"]
        return self.match_to_entities(all_dims, entities)
