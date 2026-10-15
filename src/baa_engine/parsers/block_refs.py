"""块引用提取器（P127-S1）

背景
----
图纸的构件语义（门窗、设备、柱）往往编码在**块引用（INSERT）**里：
块名（如 `DOOR_900`、`WINDOW_C1200`、天正门窗块 `M_*` / `C_*`）与块属性
（ATTRIB，如门窗编号、规格）比图层名更接近"设计意图"。

现状问题
--------
- DXF 路径：`extract_properties` 仅保留 `block_name` + `insert_x/y`，
  **丢失 ATTRIB 值、旋转、缩放**，且散落在 properties 里，难以统一消费。
- DWG 转换路径：`_insert_block_expand` 把块内实体仿射变换后写入 modelspace，
  **块名在展平瞬间被丢弃**。

本模块的作用
------------
在展平之外，独立、结构化地收集块引用语义，作为构件分类的高可信信号。
只读、不改动 modelspace，容忍 ezdxf 各版本字段缺失。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 天正（TArch）门窗等块名常带的前缀，供下游规则库参考
TZ_BLOCK_PREFIXES = ("M_", "C_", "D_", "W_", "TCH", "TZ")


@dataclass
class BlockRef:
    """单条块引用记录"""

    block_name: str
    insert_point: Optional[tuple]  # (x, y) 或 None
    rotation: float
    x_scale: float
    y_scale: float
    layer: str
    handle: str
    attribs: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "block_name": self.block_name,
            "insert_point": list(self.insert_point) if self.insert_point else None,
            "rotation": self.rotation,
            "x_scale": self.x_scale,
            "y_scale": self.y_scale,
            "layer": self.layer,
            "handle": self.handle,
            "attribs": dict(self.attribs),
        }


def _as_xy(value) -> Optional[tuple]:
    """把 Vec3/Vec2/tuple 统一成 (x, y)；失败返回 None。"""
    try:
        if hasattr(value, "x") and hasattr(value, "y"):
            return (float(value.x), float(value.y))
        if hasattr(value, "__getitem__"):
            return (float(value[0]), float(value[1]))
    except Exception as _e:
        logger.debug("[P127-S1] 坐标转换失败: %s: %s", type(_e).__name__, _e)
    return None


def _first_attr(dxf, names, default):
    """按候选名顺序取第一个存在的属性值；都不存在返回 default。

    注意：不能简单用 `getattr(...) or default`，因为 0 是合法值
    （退化缩放、零旋转），会被误判为缺失。
    """
    for n in names:
        v = getattr(dxf, n, None)
        if v is not None:
            return v
    return default


def extract_attribs(entity) -> Dict[str, str]:
    """读取 INSERT 上附着的 ATTRIB，返回 {tag: text}。

    ATTDEF 未实例化（块内只有定义、无属性实例）时返回空 dict。
    """
    out: Dict[str, str] = {}
    attribs = getattr(entity, "attribs", None)
    if not attribs:
        return out
    try:
        for attr in attribs:
            try:
                tag = attr.dxf.tag if hasattr(attr.dxf, "tag") else ""
                text = attr.dxf.text if hasattr(attr.dxf, "text") else ""
                if tag:
                    out[str(tag)] = str(text)
            except Exception as _e:
                logger.debug("[P127-S1] ATTRIB 单条解析失败: %s: %s", type(_e).__name__, _e)
    except Exception as _e:
        logger.debug("[P127-S1] ATTRIB 迭代失败: %s: %s", type(_e).__name__, _e)
    return out


def read_block_ref(entity) -> Optional[BlockRef]:
    """从单个实体读取块引用；非 INSERT 或读取失败返回 None。"""
    try:
        if not hasattr(entity, "dxftype") or entity.dxftype() != "INSERT":
            return None
    except Exception:
        return None

    try:
        dxf = entity.dxf
        block_name = dxf.name if hasattr(dxf, "name") else ""
        insert_point = _as_xy(dxf.insert) if hasattr(dxf, "insert") else None
        rotation = float(_first_attr(dxf, ("rotation",), 0.0))
        # ezdxf 的 DXF 属性名为 xscale/yscale（非 x_scale/y_scale）；
        # 兼容其他读取实现可能暴露的下划线命名。
        x_scale = float(_first_attr(dxf, ("xscale", "x_scale"), 1.0))
        y_scale = float(_first_attr(dxf, ("yscale", "y_scale"), 1.0))
        layer = _first_attr(dxf, ("layer",), "0") or "0"
        handle = _first_attr(dxf, ("handle",), "") or ""

        return BlockRef(
            block_name=str(block_name),
            insert_point=insert_point,
            rotation=rotation,
            x_scale=x_scale,
            y_scale=y_scale,
            layer=str(layer),
            handle=str(handle),
            attribs=extract_attribs(entity),
        )
    except Exception as _e:
        logger.debug("[P127-S1] INSERT 块引用读取失败: %s: %s", type(_e).__name__, _e)
        return None


def extract_block_refs(msp, max_refs: Optional[int] = None) -> List[BlockRef]:
    """扫描 modelspace，收集全部块引用。

    参数:
        msp: ezdxf modelspace（或任意可迭代实体集合）
        max_refs: 上限保护，None 表示不限制
    """
    refs: List[BlockRef] = []
    try:
        entities = list(msp)
    except Exception as _e:
        logger.warning("[P127-S1] modelspace 不可迭代: %s: %s", type(_e).__name__, _e)
        return refs

    for entity in entities:
        try:
            if entity.dxftype() != "INSERT":
                continue
        except Exception:
            continue
        ref = read_block_ref(entity)
        if ref is not None:
            refs.append(ref)
            if max_refs is not None and len(refs) >= max_refs:
                break
    return refs


def summarize_block_refs(refs: List[BlockRef]) -> dict:
    """块引用汇总：总数、按块名分布、唯一块数、ATTRIB 覆盖率。"""
    by_block: Dict[str, int] = {}
    with_attrib = 0
    for r in refs:
        by_block[r.block_name] = by_block.get(r.block_name, 0) + 1
        if r.attribs:
            with_attrib += 1
    total = len(refs)
    return {
        "total": total,
        "unique_blocks": len(by_block),
        "by_block": by_block,
        "attrib_coverage": round(with_attrib / total, 4) if total else 0.0,
    }


__all__ = [
    "BlockRef",
    "TZ_BLOCK_PREFIXES",
    "extract_attribs",
    "read_block_ref",
    "extract_block_refs",
    "summarize_block_refs",
]
