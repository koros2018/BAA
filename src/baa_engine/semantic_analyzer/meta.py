"""Meta entity parsing from META layer.
"""
from typing import List
from .models import SemanticEntity
from ..drawing_parser import RawPrimitive

def _parse_meta_entities(
    self, primitives
) -> List[
    SemanticEntity
]:
    """
    解析 META 图层的结构化实体元数据。
    格式: ENTITY:<type>|x:<x>|y:<y>|w:<w>|h:<h>|key:value|...
    用于合成图纸测试场景，跳过常规几何归并直接构建实体。
    """
    entities = []
    for prim in primitives:  # 循环
        if prim.layer.upper() != "META":  # condition: prim.layer.upper() != "META":
            continue  # 继续循环
        text = prim.properties.get("text", "")
        if not text.startswith("ENTITY:"):  # check: negated condition
            continue  # 继续循环
        parts = text.split("|")
        if len(parts) < 5:  # check: numeric comparison
            continue  # 继续循环
        # 解析类型
        etype = parts[0].replace("ENTITY:", "").strip()
        # 解析bbox和属性
        props = {}
        bbox = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
        for part in parts[1:]:  # 循环
            if ":" not in part:  # check: membership test
                continue  # 继续循环
            k, v = part.split(":", 1)  # 操作
            k = k.strip()
            v = v.strip()
            if k == "x":  # condition: k == "x":
                bbox["x"] = float(v)  # 操作
            elif k == "y":  # 分支
                bbox["y"] = float(v)  # 操作
            elif k == "w":  # 分支
                bbox["width"] = float(v)  # 操作
            elif k == "h":  # 分支
                bbox["height"] = float(v)  # 操作
            else:  # 否则
                # 尝试转数字，失败保留字符串
                try:  # 尝试
                    props[k] = float(v)
                except ValueError:  # 捕获异常
                    props[k] = v

        self._entity_counter += 1
        entity = SemanticEntity(
            entity_id=f"{etype.upper()}_{self._entity_counter:03d}",
            entity_type=etype,
            bbox=bbox,
            layer="META",
            confidence=1.0,
            properties=props,
        )  # code
        entities.append(entity)  # append: add to list

    return entities

