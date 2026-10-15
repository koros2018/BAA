"""P130: 图框/表格区域排除 —— 单元测试

验证 room.py 新增的扫线法前置过滤器：
  - _is_titleblock_layer       图层判据（复用 LAYER_RULES）
  - _detect_table_regions      几何网格识别（规则表格）
  - _detect_frame_rects        titleblock 图框区域
  - _exclude_table_and_frame_prims  编排器

设计原则：宁可漏排、不可误排。因此除了"能排掉表格"的正例，
还必须覆盖"成排相同房间不被误判为表格"的反例。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.baa_engine.drawing_parser import RawPrimitive
from src.baa_engine.semantic_analyzer import SemanticAnalyzer
from src.baa_engine.semantic_analyzer.room import (
    _collect_wall_segments,
    _detect_frame_rects,
    _detect_table_regions,
    _exclude_table_and_frame_prims,
    _is_titleblock_layer,
)

# ── 构造工具 ──


def _line(layer, handle, x0, y0, x1, y1):
    """构造一条 LINE 图元（properties 与 parsers/geometry.py 的产出格式一致）。"""
    return RawPrimitive(
        "LINE",
        layer,
        handle,
        {
            "x": min(x0, x1),
            "y": min(y0, y1),
            "width": abs(x1 - x0),
            "height": abs(y1 - y0),
        },
        {"start_point": {"x": x0, "y": y0}, "end_point": {"x": x1, "y": y1}},
    )


def _table_grid(layer="A", x0=0, y0=0, cols=9, rows=8, pitch=800):
    """构造规则表格网格：cols 条垂直线 × rows 条水平线，等距、贯穿整区。

    网格尺寸 = (cols-1)*pitch 宽 × (rows-1)*pitch 高。
    默认 8×7 = 56 个单元格（>= _TABLE_MIN_CELLS=50），
    单元格 800×800mm（远小于房间最小短边 2000mm）。
    """
    w = (cols - 1) * pitch
    h = (rows - 1) * pitch
    prims = []
    for i in range(cols):
        x = x0 + i * pitch
        prims.append(_line(layer, f"tv{i}", x, y0, x, y0 + h))
    for j in range(rows):
        y = y0 + j * pitch
        prims.append(_line(layer, f"th{j}", x0, y, x0 + w, y))
    return prims


def _room_box(layer, handle, x0, y0, w, h):
    """构造一个闭合矩形房间的 4 条墙线。"""
    return [
        _line(layer, f"{handle}_b", x0, y0, x0 + w, y0),
        _line(layer, f"{handle}_r", x0 + w, y0, x0 + w, y0 + h),
        _line(layer, f"{handle}_t", x0 + w, y0 + h, x0, y0 + h),
        _line(layer, f"{handle}_l", x0, y0 + h, x0, y0),
    ]


# ── 用例 ──


def test_titleblock_layer_helper():
    """titleblock 判据：命中规则；通用/other 图层不命中。"""
    assert _is_titleblock_layer("通-图框-图签") is True
    assert _is_titleblock_layer("通-图框") is True
    assert _is_titleblock_layer("C-SHET") is True
    assert _is_titleblock_layer("建.17.图框") is True
    # 通用短图层名不得被命中（可能在其他院是墙体层）
    assert _is_titleblock_layer("A") is False
    # 映射为 "other" 的键不参与硬排除
    assert _is_titleblock_layer("BORDER") is False
    assert _is_titleblock_layer("P-KX1") is False
    assert _is_titleblock_layer("") is False


def test_detect_table_grid():
    """规则表格网格（等距、贯穿整区、单元格远小于房间）应被识别为一个区域。"""
    prims = _table_grid()
    segs = _collect_wall_segments(prims)
    assert len(segs) == 17

    regions = _detect_table_regions(segs)
    assert len(regions) == 1
    r = regions[0]
    assert r["width"] == pytest.approx(6400.0)
    assert r["height"] == pytest.approx(5600.0)


def test_excludes_table_but_keeps_room():
    """表格被剔除；远端的真实房间保留，且解析出 room == 1。"""
    table = _table_grid(layer="A")
    room = _room_box("WALL", "room1", 100000, 0, 8000, 6000)
    prims = table + room

    kept = _exclude_table_and_frame_prims(prims, prims)
    kept_handles = {p.handle for p in kept}
    assert kept_handles == {"room1_b", "room1_r", "room1_t", "room1_l"}

    analyzer = SemanticAnalyzer()
    rooms = analyzer._sweep_line_detect_rooms(prims)
    assert len(rooms) == 1
    assert rooms[0].type == "room"


def test_keeps_rooms_in_a_row():
    """3 个尺寸相同的成排房间不得被误判为表格。

    构造：3 个 3000×4000 房间沿 X 排列，房间之间留 500mm 间隙
    （等价于水平墙被门洞/墙垛打断，不满足"贯穿整区"判据）。
    房间尺寸一律、间距一律 → 贴近"规则的成排模块"，是表格误判的高危场景。
    """
    prims = []
    for i in range(3):
        prims.extend(_room_box("WALL", f"r{i}", i * 3500, 0, 3000, 4000))

    segs = _collect_wall_segments(prims)
    assert _detect_table_regions(segs) == []

    kept = _exclude_table_and_frame_prims(prims, prims)
    assert len(kept) == len(prims)

    analyzer = SemanticAnalyzer()
    rooms = analyzer._sweep_line_detect_rooms(prims)
    assert len(rooms) == 3


def test_frame_insert_bbox_excluded():
    """titleblock 图框：边框线被剔除，但图框内部的墙线必须保留。"""
    frame = RawPrimitive(
        "INSERT",
        "通-图框-图签",
        "frame1",
        {"x": 0, "y": 0, "width": 90000, "height": 60000},
        {},
    )
    border = _line("A", "b1", 0, 0, 90000, 0)  # 贴在图框底边上
    inside = _line("A", "in1", 1000, 5000, 5000, 5000)  # 图框内部的墙线

    rects = _detect_frame_rects([frame, border, inside], _collect_wall_segments([border, inside]))
    assert len(rects) == 1
    assert rects[0]["width"] == pytest.approx(90000.0)

    kept = _exclude_table_and_frame_prims([border, inside], [frame, border, inside])
    # 边框被剔除，内部墙线保留（关键：不得把图框内部的房间清空）
    assert {p.handle for p in kept} == {"in1"}


def test_no_regions_leaves_prims_unchanged():
    """无表格、无图框时，过滤器不改变输入。"""
    prims = _room_box("WALL", "room1", 0, 0, 8000, 6000)
    kept = _exclude_table_and_frame_prims(prims, prims)
    assert len(kept) == len(prims)
    assert {p.handle for p in kept} == {p.handle for p in prims}
