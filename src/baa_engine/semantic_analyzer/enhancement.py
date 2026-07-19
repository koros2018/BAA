"""
BAA 语义识别引擎 — YOLO 增强
YOLO 检测增强 / 结果合并
"""

from typing import List, Dict, Optional
from .models import SemanticEntity
from ..drawing_parser import RawPrimitive


def _yolo_enhance_impl(
    self, dxf_path: str
) -> List[SemanticEntity]:  # method: def _yolo_enhance(self, dxf_path: str) -> List[SemanticEntit
    """对 DXF 执行 YOLO 检测，返回增强实体列表

    当前只保留 YOLO 检测精度高的实体类型：
    - room (mAP50=0.995)：房间检测极准确
    - corridor (mAP50=0.709)：走廊检测良好
    """
    from .yolo_integrator import YOLODetectionIntegrator  # 导入

    integrator = YOLODetectionIntegrator()  # assign
    if not integrator.load_model():  # check: negated condition
        logger.warning("YOLO 模型加载失败")  # call
        return []  # return: list of items

    # 渲染 DXF 并预测
    image_path, detections = integrator.render_and_predict(dxf_path, dpi=72)  # assign
    if not image_path or not detections:  # check: negated condition
        return []  # return: list of items

    # 只保留高精度类型（room, corridor）
    # room mAP50=0.995, corridor mAP50=0.709
    HIGH_CONF_TYPES = {"room", "corridor"}  # assign
    filtered = [
        d for d in detections if d["type"] in HIGH_CONF_TYPES and d["confidence"] >= 0.35
    ]  # assign: membership check

    # 对 room 类型：过滤掉 bbox 面积过小或过大的（不合理房间）
    # YOLO 的 bbox 是像素坐标，需要先转为世界坐标再判断面积
    # 用 bbox 的像素宽高比辅助判断：房间应该是矩形（宽高比 < 3）
    filtered = [
        d
        for d in filtered
        if d["type"] != "room"
        or (  # compare: inequality
            d["bbox"]["width"] > 20
            and d["bbox"]["height"] > 20  # 最小尺寸 20 像素
            and max(d["bbox"]["width"], d["bbox"]["height"])
            / max(d["bbox"]["height"], d["bbox"]["width"], 1)
            < 5.0  # 宽高比 < 5
        )
    ]  # code

    # P25: YOLO 后置规则层兜底过滤
    from .yolo_integrator import filter_yolo_detections  # import: YOLO integrator

    filtered = filter_yolo_detections(filtered, verbose=True)  # assign

    if not filtered:  # check: negated condition
        return []  # return: list of items

    # 转换为 SemanticEntity
    entities = []  # init: empty list
    for det in filtered:  # 循环
        self._entity_counter += 1  # assign: self attribute
        entity = SemanticEntity(  # assign
            entity_id=f"YOLO_{det['type'].upper()}_{self._entity_counter:03d}",  # assign
            entity_type=det["type"],  # assign
            bbox=det["bbox"],  # assign
            layer="YOLO",  # assign
            confidence=det["confidence"],  # assign
            properties={  # assign
                **det.get("properties", {}),  # 展开
                "detection_source": "yolo",  # 字段
            },  # code
        )  # code
        entities.append(entity)  # append: add to list

    # 清理临时图片
    try:  # 尝试
        os.remove(image_path)  # remove: delete item
    except Exception:  # 捕获异常
        pass  # 忽略

    return entities  # return


def _merge_yolo_results_impl(
    self,
    rule_entities: List[
        SemanticEntity
    ],  # method: def _merge_yolo_results(self, rule_entities: List[SemanticEn
    yolo_entities: List[SemanticEntity],
) -> List[SemanticEntity]:  # code
    """合并规则解析和 YOLO 检测的实体

    策略：
    1. 规则解析的实体优先保留（含已识别的 room）
    2. YOLO 检测的 room/corridor 只在规则未识别到时添加
    3. 通过 IOU 判断重叠——YOLO 框与规则框高度重叠时不重复添加
    4. YOLO 实体标记 detection_source="yolo"，原子函数对 YOLO 实体放宽判定
    """
    if not yolo_entities:  # check: negated condition
        return rule_entities  # return

    merged = list(rule_entities)  # assign
    added_ids = set()  # init: empty set

    for yolo_ent in yolo_entities:  # 循环
        yolo_bbox = yolo_ent.bbox  # assign
        yolo_center_x = yolo_bbox["x"] + yolo_bbox["width"] / 2  # assign
        yolo_center_y = yolo_bbox["y"] + yolo_bbox["height"] / 2  # assign

        # 检查是否与规则实体重叠
        is_duplicate = False  # assign
        for rule_ent in rule_entities:  # 循环
            # 只检查同类型（room 可能被归为 wall，所以放宽限制）
            if yolo_ent.type == "room" and rule_ent.type not in (
                "room",
                "wall",
            ):  # check: membership test
                continue  # 继续循环
            if yolo_ent.type == "corridor" and rule_ent.type != "corridor":  # check: OR condition
                continue  # 继续循环

            rule_bbox = rule_ent.bbox  # assign
            # 检查 YOLO 中心点是否在规则实体的 bbox 内
            if (
                rule_bbox["x"]
                <= yolo_center_x
                <= rule_bbox["x"] + rule_bbox["width"]  # check: numeric comparison
                and rule_bbox["y"] <= yolo_center_y <= rule_bbox["y"] + rule_bbox["height"]
            ):  # assign
                is_duplicate = True  # assign
                break  # 跳出循环

            # 计算 IOU
            inter_x = max(
                0,
                min(
                    yolo_bbox["x"] + yolo_bbox["width"], rule_bbox["x"] + rule_bbox["width"]
                )  # assign
                - max(yolo_bbox["x"], rule_bbox["x"]),
            )  # max: get maximum
            inter_y = max(
                0,
                min(
                    yolo_bbox["y"] + yolo_bbox["height"], rule_bbox["y"] + rule_bbox["height"]
                )  # assign
                - max(yolo_bbox["y"], rule_bbox["y"]),
            )  # max: get maximum
            union = (
                yolo_bbox["width"] * yolo_bbox["height"]
                + rule_bbox["width"] * rule_bbox["height"]
                - inter_x * inter_y
            )  # assign
            iou = (inter_x * inter_y) / max(union, 1)  # assign
            if iou > 0.3:  # check: numeric comparison
                is_duplicate = True  # assign
                break  # 跳出循环

        if not is_duplicate and yolo_ent.id not in added_ids:  # check: membership test
            # YOLO 实体标记检测来源，原子函数会据此放宽尺寸相关判定
            yolo_ent.properties["detection_source"] = "yolo"  # 操作
            # 对 YOLO 检测的 room 不设置 area 属性（bbox 映射不精确）
            if yolo_ent.type == "room":  # condition: yolo_ent.type == "room":
                yolo_ent.properties.pop("area", None)  # 操作
            merged.append(yolo_ent)  # append: add to list
            added_ids.add(yolo_ent.id)  # call

    return merged  # return
