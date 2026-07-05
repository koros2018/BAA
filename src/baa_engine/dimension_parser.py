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
from typing import List, Dict, Any, Optional, Tuple  # typing: type hints
from pathlib import Path  # import: path utils


class DimensionParser:  # class definition
    """尺寸标注解析器"""

    # 哪些实体类型需要从 DIMENSION 获取实际尺寸
    DIMENSIONABLE_TYPES = {"door", "window", "fire_door", "fire_window",  # assignment
                           "corridor", "staircase", "fire_lane", "room",  # 目标实体类型
                           "wall", "exit"}  # 目标实体类型

    # 尺寸值单位的猜测（mm 还是 m）
    # 真实 DXF 中 DIMENSION 通常是 mm 单位
    # 合成 DXF 中可能是 mm 或 m

    def extract_dimensions(self, file_path: str) -> List[Dict]:  # function: def extract_dimensions(self, file_path: str) -> List[Dict]:
        """从图纸中提取 DIMENSION 实体"""
        ext = Path(file_path).suffix.lower()  # function call
        dimensions = []  # assignment

        if ext == ".dwg":  # condition: ext == ".dwg":
            # DWG：直接用 ezdwg 读 DIMENSION 的 dxf 字典
            try:  # 尝试
                import ezdwg  # import
                dwg_doc = ezdwg.read(file_path)  # function call
                msp = dwg_doc.modelspace()  # function call
                try:  # 尝试
                    dim_ents = list(msp.query(types="DIMENSION"))  # function call
                except Exception:  # 捕获异常
                    try:  # 尝试
                        dim_ents = list(msp.query(types=['DIMENSION']))  # function call
                    except Exception:  # 捕获异常
                        dim_ents = []  # assignment
                for ent in dim_ents:  # 循环
                    try:  # 尝试
                        d = ent.dxf  # assignment
                        # ezdwg 的 measurement 字段名为 actual_measurement
                        meas = d.get("actual_measurement", d.get("measurement", None))  # function call
                        if meas is None or meas <= 0.1:  # check: value is None
                            continue  # 继续循环
                        defp2 = d.get("defpoint2", (0, 0, 0))  # function call
                        defp3 = d.get("defpoint3", (0, 0, 0))  # function call
                        text_mid = d.get("text_midpoint", (0, 0, 0))  # function call
                        dimensions.append({  # code
                            "handle": d.get("handle", ""),  # 字段
                            "layer": d.get("layer", "0"),  # 字段
                            "measurement": float(meas),  # 字段
                            "text": d.get("text", ""),  # 字段
                            "dimtype": d.get("dimtype", 0),  # 字段
                            "defpoint2": {"x": defp2[0], "y": defp2[1]},  # 字段
                            "defpoint3": {"x": defp3[0], "y": defp3[1]},  # 字段
                            "text_midpoint": {"x": text_mid[0], "y": text_mid[1]},  # 字段
                        })  # code
                    except Exception:  # 捕获异常
                        continue  # 继续循环
            except Exception as e:  # 捕获异常
                pass  # 占位
        else:  # 否则
            # DXF：用 ezdxf 读
            try:  # 尝试
                import ezdxf  # import
                doc = ezdxf.readfile(file_path)  # function call
                msp = doc.modelspace()  # function call
                for entity in msp:  # 循环
                    if entity.dxftype() != "DIMENSION":  # condition: entity.dxftype() != "DIMENSION":
                        continue  # 继续循环
                    try:  # 尝试
                        meas = entity.get_measurement()  # function call
                        if meas is None or meas <= 0.1:  # check: value is None
                            continue  # 继续循环
                        dimensions.append({  # code
                            "handle": entity.dxf.handle if hasattr(entity.dxf, 'handle') else '',  # 字段
                            "layer": entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0',  # 字段
                            "measurement": float(meas),  # 字段
                            "text": entity.get_measurement_text() if hasattr(entity, 'get_measurement_text') else str(meas),  # 字段
                            "dimtype": str(entity.dxf.dimtype) if hasattr(entity.dxf, 'dimtype') else 'LINEAR',  # 字段
                            "defpoint2": {"x": entity.dxf.defpoint2.x if hasattr(entity.dxf.defpoint2, 'x') else 0,  # 字段
                                          "y": entity.dxf.defpoint2.y if hasattr(entity.dxf.defpoint2, 'y') else 0},  # 字段
                            "defpoint3": {"x": entity.dxf.defpoint3.x if hasattr(entity.dxf.defpoint3, 'x') else 0,  # 字段
                                          "y": entity.dxf.defpoint3.y if hasattr(entity.dxf.defpoint3, 'y') else 0},  # 字段
                            "text_midpoint": {"x": entity.dxf.text_midpoint.x if hasattr(entity.dxf, 'text_midpoint') and hasattr(entity.dxf.text_midpoint, 'x') else 0,  # 字段
                                              "y": entity.dxf.text_midpoint.y if hasattr(entity.dxf, 'text_midpoint') and hasattr(entity.dxf.text_midpoint, 'y') else 0},  # 字段
                        })  # code
                    except Exception:  # 捕获异常
                        continue  # 继续循环
            except Exception:  # 捕获异常
                pass  # 占位

        return dimensions  # return

    def classify_dimensions(self, dimensions: List[Dict]) -> Dict[str, List[Dict]]:  # function: def classify_dimensions(self, dimensions: List[Dict]) -> Dic
        """按用途分类尺寸标注

        返回:
            {"width": [...], "height": [...], "length": [...], "other": [...]}
        """
        classified = {"width": [], "height": [], "length": [], "other": []}  # assignment

        for dim in dimensions:  # 循环
            meas = dim.get("measurement", 0)  # function call
            dp2 = dim.get("defpoint2", {})  # function call
            dp3 = dim.get("defpoint3", {})  # function call
            text = dim.get("text", "")  # function call

            # 计算方向向量
            dx = abs(dp3.get("x", 0) - dp2.get("x", 0))  # function call
            dy = abs(dp3.get("y", 0) - dp2.get("y", 0))  # function call

            # 水平 → width/长度，垂直 → height
            if dx > dy * 2:  # check: numeric comparison
                classified["width"].append(dim)  # 操作
            elif dy > dx * 2:  # 条件分支
                classified["height"].append(dim)  # 操作
            else:  # 否则
                classified["length"].append(dim)  # 操作

        return classified  # return

    def match_to_entities(self, dimensions: List[Dict],  # function: def match_to_entities(self, dimensions: List[Dict],
                          entities: List[Dict],  # 操作
                          max_distance: float = 5.0) -> List[Dict]:  # assignment
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
        import math  # stdlib: math
        
        if not entities or not dimensions:  # check: negated condition
            return entities  # return

        # 预处理：计算每个实体的中心和边界
        entity_info = []  # assignment
        for i, e in enumerate(entities):  # 循环
            bbox = e.get("bbox", {})  # function call
            cx = bbox.get("x", 0) + bbox.get("width", 0) / 2  # function call
            cy = bbox.get("y", 0) + bbox.get("height", 0) / 2  # function call
            x1 = bbox.get("x", 0)  # function call
            y1 = bbox.get("y", 0)  # function call
            x2 = x1 + bbox.get("width", 0)  # function call
            y2 = y1 + bbox.get("height", 0)  # function call
            entity_info.append({  # code
                "idx": i,  # 字段
                "cx": cx, "cy": cy,  # 字段
                "x1": x1, "y1": y1,  # 字段
                "x2": x2, "y2": y2,  # 字段
            })  # code

        matched_dims = set()  # function call
        
        # 对每个 DIMENSION，先用距离找候选，再用方向+投影约束筛选
        for dim in dimensions:  # 循环
            tmid = dim.get("text_midpoint", {})  # function call
            dmx, dmy = tmid.get("x", 0), tmid.get("y", 0)  # 操作
            dp2 = dim.get("defpoint2", {})  # function call
            dp3 = dim.get("defpoint3", {})  # function call
            
            # 计算标注方向向量
            dx_vec = abs(dp3.get("x", 0) - dp2.get("x", 0))  # function call
            dy_vec = abs(dp3.get("y", 0) - dp2.get("y", 0))  # function call
            is_horizontal = dx_vec > dy_vec * 2  # assignment
            is_vertical = dy_vec > dx_vec * 2  # assignment
            
            # 标注的两个端点坐标
            d2x, d2y = dp2.get("x", 0), dp2.get("y", 0)  # 操作
            d3x, d3y = dp3.get("x", 0), dp3.get("y", 0)  # 操作
            # defpoint 最小/最大
            dp_xmin, dp_xmax = min(d2x, d3x), max(d2x, d3x)  # 解包
            dp_ymin, dp_ymax = min(d2y, d3y), max(d2y, d3y)  # 解包

            best_dist = float("inf")  # function call
            best_idx = None  # assignment
            best_projection = -1.0  # 投影重叠度

            for info in entity_info:  # 循环
                # 距离筛选：text_midpoint 到实体中心
                dist = ((dmx - info["cx"]) ** 2 + (dmy - info["cy"]) ** 2) ** 0.5  # function call
                if dist > max_distance * 2000:  # 放宽初始阈值
                    continue  # 继续循环
                
                # 投影约束：DIM 的 defpoint 投影必须在实体 bbox 范围内
                if is_horizontal:  # check: OR condition
                    # 水平标注：y 方向投影重叠
                    proj_overlap = max(0, min(info["y2"], dp_ymax) - max(info["y1"], dp_ymin))  # get maximum
                    ent_h = info["y2"] - info["y1"]  # assignment
                    if ent_h > 0:  # check: numeric comparison
                        proj_ratio = proj_overlap / ent_h  # assignment
                    else:  # 否则
                        proj_ratio = 0  # assignment
                    # x 方向端点必须在实体投影范围内
                    x_overlap = max(0, min(info["x2"], dp_xmax) - max(info["x1"], dp_xmin))  # get maximum
                elif is_vertical:  # 条件分支
                    # 垂直标注：x 方向投影重叠
                    proj_overlap = max(0, min(info["x2"], dp_xmax) - max(info["x1"], dp_xmin))  # get maximum
                    ent_w = info["x2"] - info["x1"]  # assignment
                    if ent_w > 0:  # check: numeric comparison
                        proj_ratio = proj_overlap / ent_w  # assignment
                    else:  # 否则
                        proj_ratio = 0  # assignment
                    y_overlap = max(0, min(info["y2"], dp_ymax) - max(info["y1"], dp_ymin))  # get maximum
                else:  # 否则
                    # 斜向标注：用整体 IoU
                    proj_overlap = 0  # assignment
                    proj_ratio = 0  # assignment
                
                # 组合评分：距离 + 投影重叠
                score = dist * (1.5 - min(proj_ratio, 1.0))  # get minimum
                
                if score < best_dist or (abs(score - best_dist) < 1 and proj_ratio > best_projection):  # check: numeric comparison
                    best_dist = score  # assignment
                    best_idx = info["idx"]  # assignment
                    best_projection = proj_ratio  # assignment

            if best_idx is not None:  # check: value is not None
                meas = dim.get("measurement", 0)  # function call

                if "properties" not in entities[best_idx]:  # check: membership test
                    entities[best_idx]["properties"] = {}  # 操作

                props = entities[best_idx]["properties"]  # assignment

                # 单位转换优化（V2）：
                # 用 min(原始值, 原始值/1000) 双重检查
                # 如果原始值>100且除以1000后更合理（0.3~30m），取除以1000
                if meas > 100 and 0.3 < meas / 1000 < 30:  # check: numeric comparison
                    meas_m = meas / 1000.0  # assignment
                elif meas > 10000 and 0.3 < meas / 1000 < 30:  # 条件分支
                    meas_m = meas / 1000.0  # assignment
                else:  # 否则
                    meas_m = meas  # assignment
                
                # 根据方向注入
                if is_horizontal:  # check: OR condition
                    if "width" not in props or props.get("detection_source") != "yolo":  # check: membership test
                        props["width"] = meas_m  # 操作
                        props["clear_width"] = meas_m  # 操作
                        props["_dimension_source"] = "dimension"  # 操作
                        props["_dimension_raw"] = meas  # 操作
                elif is_vertical:  # 条件分支
                    if "height" not in props:  # check: membership test
                        props["height"] = meas_m  # 操作
                        props["_dimension_source"] = "dimension"  # 操作
                        props["_dimension_raw"] = meas  # 操作
                else:  # 否则
                    props["length"] = meas_m  # 操作
                    props["_dimension_source"] = "dimension"  # 操作
                    props["_dimension_raw"] = meas  # 操作

                matched_dims.add(id(dim))  # function call

        return entities  # return

    def inject_into_entities(self, dimensions: List[Dict],  # function: def inject_into_entities(self, dimensions: List[Dict],
                              entities: List[Dict]) -> List[Dict]:  # 操作
        """提取 + 分类 + 匹配 + 注入 一键完成"""
        classified = self.classify_dimensions(dimensions)  # function call
        all_dims = classified["width"] + classified["height"] + classified["length"]  # assignment
        return self.match_to_entities(all_dims, entities)  # return: self
