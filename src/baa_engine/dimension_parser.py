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

import logging

logger = logging.getLogger(__name__)

from typing import List, Dict
from pathlib import Path

# 评分/投影/单位换算与语义分析主干共用同一套实现（relations.py），
# 避免 dimension_parser 与 relations._bind_dimensions 出现两套并行逻辑。
from .semantic_analyzer.relations import (
    _dim_orientation,
    _dim_projection_ratio,
    _dim_match_score,
    _measurement_to_meters,
)


class DimensionParser:
    """尺寸标注解析器

    从 DXF/DWG 图纸中提取 DIMENSION 实体并匹配到附近建筑实体。
    核心流程：extract → classify → match → inject。

    设计约束：
    - DIMENSION 是 AutoCAD 中标注尺寸的特殊实体，非几何图元（LINE/CIRCLE）
    - 一个 DIMENSION 包含 measurement（测量值）、defpoint（定义点）、text_midpoint（文字位置）
    - 通过 defpoint 方向区分水平/垂直标注，对应实体的 width/height 属性
    - 单位混乱（mm vs m）是建筑图纸的常见问题，需要双重检查
    """

    # 哪些实体类型需要从 DIMENSION 获取实际尺寸
    # DIMENSIONABLE_TYPES 筛选规则：仅门/窗/走廊/楼梯/房间/墙体/安全出口
    # 需要从 DIMENSION 获取实际尺寸，因为这些实体的宽度/高度
    # 在图纸中通常通过尺寸标注而非几何图元直接给出
    # 注意：shaft/exit_sign/sprinkler 等设备类实体不在此列，
    # 因为它们的尺寸由设计规范硬性规定而非图纸标注决定
    DIMENSIONABLE_TYPES = {
        "door",
        "window",
        "fire_door",
        "fire_window",
        "corridor",
        "staircase",
        "fire_lane",
        "room",
        "wall",
        "exit",
    }

    # 尺寸值单位的猜测（mm 还是 m）
    # 真实 DXF 中 DIMENSION 通常是 mm 单位
    # 合成 DXF 中可能是 mm 或 m
    # 单位判断策略在 match_to_entities 中实现：
    # 原始值 > 100 且 /1000 后落在 0.3~30m 范围时，推测为 mm→m 转换

    def extract_dimensions(self, file_path: str) -> List[Dict]:
        """从图纸中提取 DIMENSION 实体"""
        ext = Path(file_path).suffix.lower()
        dimensions = []

        if ext == ".dwg":
            # DWG 分支：使用 ezdwg 库读取二进制 DWG 格式
            # DWG 是 Autodesk 专有格式，ezdwg 是唯一能直接读取的 Python 库
            # 与 DXF 不同，DWG 的 DIMENSION 实体字段名可能为 actual_measurement（ezdwg 特有别名）
            try:
                import ezdwg

                dwg_doc = ezdwg.read(file_path)
                msp = dwg_doc.modelspace()
                # ezdwg 不同版本的 query API 签名不一致，需兼容两种传参形式
                try:
                    dim_ents = list(msp.query(types="DIMENSION"))
                except Exception:
                    try:
                        dim_ents = list(msp.query(types=["DIMENSION"]))
                    except Exception:
                        dim_ents = []
                for ent in dim_ents:
                    try:
                        d = ent.dxf
                        # ezdwg 将 AutoCAD DXF 的 measurement 字段映射为 actual_measurement
                        # 部分版本也保留 measurement 字段，优先取 actual_measurement 以防空值
                        meas = d.get("actual_measurement", d.get("measurement", None))
                        # 阈值 0.1：过滤无效或零值标注（AutoCAD 中最小实际尺寸单位为 mm，<0.1mm 无意义）
                        if meas is None or meas <= 0.1:
                            continue
                        # defpoint2/defpoint3：AutoCAD DIMENSION 的两个定义点，决定了标注的方向和长度
                        # 水平标注的 defpoint2 在左端、defpoint3 在右端；垂直标注同理
                        defp2 = d.get("defpoint2", (0, 0, 0))
                        defp3 = d.get("defpoint3", (0, 0, 0))
                        text_mid = d.get("text_midpoint", (0, 0, 0))
                        dimensions.append(
                            {
                                "handle": d.get("handle", ""),
                                "layer": d.get("layer", "0"),
                                "measurement": float(meas),
                                "text": d.get("text", ""),
                                "dimtype": d.get("dimtype", 0),
                                # defpoint2/defpoint3 仅保留 xy 平面坐标，z 轴在建筑平面图中无需关心
                                "defpoint2": {"x": defp2[0], "y": defp2[1]},
                                "defpoint3": {"x": defp3[0], "y": defp3[1]},
                                "text_midpoint": {"x": text_mid[0], "y": text_mid[1]},
                            }
                        )
                    except Exception:
                        # 单个实体解析失败不影响其他标注，跳过继续
                        continue
            except Exception as _e:
                # P120 异常处理全量修复：DWG 文件损坏或 ezdwg 未安装时静默降级，不抛异常阻塞整体流程，但记录日志
                logger.warning(
                    "[P120] DWG 尺寸标注提取失败（降级跳过）: %s: %s", type(_e).__name__, _e
                )
        else:
            # DXF 分支：使用 ezdxf 库读取开放的 DXF 格式
            # DXF 是 AutoCAD 公开格式，ezdxf 社区支持优于 ezdwg
            try:
                import ezdxf

                doc = ezdxf.readfile(file_path)
                msp = doc.modelspace()
                for entity in msp:
                    # 只处理 DIMENSION 实体类型，跳过几何图元（LINE/CIRCLE/TEXT 等）
                    # 几何图元不包含 measurement 值，无法反推尺寸
                    if entity.dxftype() != "DIMENSION":
                        continue
                    try:
                        meas = entity.get_measurement()
                        # 阈值 0.1：与 DWG 分支一致，排除零值/无效标注
                        # AutoCAD 中实际尺寸不可能小于 0.1mm
                        if meas is None or meas <= 0.1:
                            continue
                        dimensions.append(
                            {
                                "handle": (
                                    entity.dxf.handle if hasattr(entity.dxf, "handle") else ""
                                ),
                                "layer": entity.dxf.layer if hasattr(entity.dxf, "layer") else "0",
                                "measurement": float(meas),
                                # get_measurement_text() 返回用户自定义标注文本（含前缀/后缀）
                                # 当无自定义文本时返回 str(meas) 作为 fallback
                                "text": (
                                    entity.get_measurement_text()
                                    if hasattr(entity, "get_measurement_text")
                                    else str(meas)
                                ),
                                "dimtype": (
                                    str(entity.dxf.dimtype)
                                    if hasattr(entity.dxf, "dimtype")
                                    else "LINEAR"
                                ),
                                # defpoint2/defpoint3 的 x/y 属性需要 hasattr 保护：
                                # ezdxf 不同版本对 Vec2 对象的行为有差异，部分版本返回元组而非 Vec2
                                "defpoint2": {
                                    "x": (
                                        entity.dxf.defpoint2.x
                                        if hasattr(entity.dxf.defpoint2, "x")
                                        else 0
                                    ),
                                    "y": (
                                        entity.dxf.defpoint2.y
                                        if hasattr(entity.dxf.defpoint2, "y")
                                        else 0
                                    ),
                                },
                                "defpoint3": {
                                    "x": (
                                        entity.dxf.defpoint3.x
                                        if hasattr(entity.dxf.defpoint3, "x")
                                        else 0
                                    ),
                                    "y": (
                                        entity.dxf.defpoint3.y
                                        if hasattr(entity.dxf.defpoint3, "y")
                                        else 0
                                    ),
                                },
                                "text_midpoint": {
                                    "x": (
                                        entity.dxf.text_midpoint.x
                                        if hasattr(entity.dxf, "text_midpoint")
                                        and hasattr(entity.dxf.text_midpoint, "x")
                                        else 0
                                    ),
                                    "y": (
                                        entity.dxf.text_midpoint.y
                                        if hasattr(entity.dxf, "text_midpoint")
                                        and hasattr(entity.dxf.text_midpoint, "y")
                                        else 0
                                    ),
                                },
                            }
                        )
                    except Exception:
                        continue
            except Exception as _e:
                logger.warning(
                    "[P120] DXF 尺寸标注提取失败（降级跳过）: %s: %s", type(_e).__name__, _e
                )

        return dimensions

    def classify_dimensions(self, dimensions: List[Dict]) -> Dict[str, List[Dict]]:
        """按用途分类尺寸标注

        返回:
            {"width": [...], "height": [...], "length": [...], "other": [...]}
        """
        classified = {"width": [], "height": [], "length": [], "other": []}

        for dim in dimensions:
            dp2 = dim.get("defpoint2", {})
            dp3 = dim.get("defpoint3", {})

            # 通过 defpoint2→defpoint3 的向量判断标注方向
            # 建筑图纸约定：水平尺寸标注对应宽度（width），垂直尺寸标注对应高度（height）
            dx = abs(dp3.get("x", 0) - dp2.get("x", 0))
            dy = abs(dp3.get("y", 0) - dp2.get("y", 0))

            # 阈值系数 2：允许标注线与轴线有小角度偏差（<26.6°），
            # 避免因 AutoCAD 绘图精度误差导致方向误判
            # 非水平/非垂直的标注（如斜向楼梯）归为 length 类
            if dx > dy * 2:
                classified["width"].append(dim)
            elif dy > dx * 2:
                classified["height"].append(dim)
            else:
                classified["length"].append(dim)

        return classified

    def match_to_entities(
        self, dimensions: List[Dict], entities: List[Dict], max_distance: float = 5.0
    ) -> List[Dict]:
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
        if not entities or not dimensions:
            return entities

        # 预处理：计算每个实体的 bbox 中心和边界
        # 提前计算好所有实体信息避免循环内重复计算
        entity_info = []
        for i, e in enumerate(entities):
            bbox = e.get("bbox", {})
            cx = bbox.get("x", 0) + bbox.get("width", 0) / 2
            cy = bbox.get("y", 0) + bbox.get("height", 0) / 2
            x1 = bbox.get("x", 0)
            y1 = bbox.get("y", 0)
            x2 = x1 + bbox.get("width", 0)
            y2 = y1 + bbox.get("height", 0)
            entity_info.append(
                {
                    "idx": i,
                    "cx": cx,
                    "cy": cy,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "bbox": bbox,
                }
            )

        matched_dims = set()

        # V2 匹配策略：三步约束法
        # 1. 距离筛选：text_midpoint 到实体中心距离
        # 2. 方向约束：水平标注→width，垂直标注→height
        # 3. 投影约束：defpoint 在实体 bbox 轴向上的重叠比例
        #    解决跨多个实体的大尺寸标注被误匹配到远处实体的问题
        for dim in dimensions:
            tmid = dim.get("text_midpoint", {})
            dmx, dmy = tmid.get("x", 0), tmid.get("y", 0)

            # 标注方向与 defpoint 投影重叠度：复用 relations 共享实现，
            # 与 relations._bind_dimensions 保持单一逻辑源（消除并行实现）
            orientation = _dim_orientation(dim)

            best_dist = float("inf")
            best_idx = None
            best_projection = -1.0

            for info in entity_info:
                # 距离筛选：text_midpoint 到实体中心的欧几里得距离
                dist = ((dmx - info["cx"]) ** 2 + (dmy - info["cy"]) ** 2) ** 0.5
                # max_distance 默认为 5.0（DWG/DXF 坐标系单位），乘以 2000 放宽到 10000
                # 因为 DIMENSION 标注通常位于实体旁边而非正中心，过严的距离阈值会漏匹配
                if dist > max_distance * 2000:
                    continue

                # 投影约束 + 组合评分：score = dist * (1.5 - proj_ratio)
                # 投影重叠度越高距离权重越低，优先选中被标注线穿过/正对的实体
                proj_ratio = _dim_projection_ratio(dim, info["bbox"], orientation)
                score = _dim_match_score(dist, proj_ratio)

                # 评分接近（差 < 1）时选投影重叠度更高的实体
                if score < best_dist or (
                    abs(score - best_dist) < 1 and proj_ratio > best_projection
                ):
                    best_dist = score
                    best_idx = info["idx"]
                    best_projection = proj_ratio

            if best_idx is not None:
                meas = dim.get("measurement", 0)
                # 单位换算：复用 relations 共享实现，mm→m 判据单一来源
                meas_m = _measurement_to_meters(meas)
                if meas_m is None:
                    # 0/缺失标注不注入
                    continue

                if "properties" not in entities[best_idx]:
                    entities[best_idx]["properties"] = {}

                props = entities[best_idx]["properties"]

                # 根据方向注入属性（orientation 由共享实现给出）
                # 'h'→width：水平尺寸标注对应门/窗宽度
                # 'v'→height：垂直尺寸标注对应高度（层高方向）
                # 其他（斜向）→length：楼梯斜长/坡道长度等
                # YOLO 检测的宽度优先保留（props.get("detection_source") == "yolo"），
                # 因为 YOLO 的宽高比更准确，DIMENSION 只补充 YOLO 没有的维度
                if orientation == "h":
                    if "width" not in props or props.get("detection_source") != "yolo":
                        props["width"] = meas_m
                        props["clear_width"] = meas_m
                        props["_dimension_source"] = "dimension"
                        props["_dimension_raw"] = meas
                elif orientation == "v":
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

    def inject_into_entities(self, dimensions: List[Dict], entities: List[Dict]) -> List[Dict]:
        """一键完成：提取 → 分类 → 匹配 → 注入

        这是 DimensionParser 对外的统一接口，调用方无需关心内部三步流程。
        注意：classified["other"] 被丢弃，因为方向不明的标注
        （如角度标注、直径标注）无法确定注入到实体的哪个属性。
        """
        classified = self.classify_dimensions(dimensions)
        all_dims = classified["width"] + classified["height"] + classified["length"]
        return self.match_to_entities(all_dims, entities)
