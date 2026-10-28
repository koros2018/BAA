"""T-C8 IFC/STEP 输出 单元测试 + 验收。

覆盖：
- 墙/柱/门/窗足迹矩形换算（wall_rect_mm 等）
- IFC4 导出/读回（IfcOpenShell 缺失时 skip）
- STEP 导出/读回（CadQuery 缺失时 skip）
- Hausdorff 2D 度量口径
- 验收：5 张合成 T3 平面图（不同布局）导出 IFC4 + STEP，
  墙足迹 Hausdorff 距离 ≤ 2mm
"""

import os

import pytest

from src.baa_engine.geometry_metrics import hausdorff_2d
from src.baa_engine.ifc_export import (
    column_rect_mm,
    door_rect_mm,
    ifc_available,
    wall_rect_mm,
    window_rect_mm,
)
from src.baa_engine.step_export import step_available

IFC_MARK = pytest.mark.skipif(not ifc_available(), reason="ifcopenshell 未安装")
STEP_MARK = pytest.mark.skipif(not step_available(), reason="cadquery 未安装")


def _pymupdf_independent_doc():
    return pytest.importorskip("ezdxf")


# ── 足迹矩形换算 ──────────────────────────────────────────


def test_wall_rect_horizontal():
    seg = {"orientation": "h", "pos": 4100.0, "start": 0.0, "end": 6000.0, "thickness": 200.0}
    assert wall_rect_mm(seg) == (0.0, 4000.0, 6000.0, 4200.0)


def test_wall_rect_vertical_and_reversed_span():
    seg = {"orientation": "v", "pos": 100.0, "start": 4200.0, "end": 0.0, "thickness": 200.0}
    assert wall_rect_mm(seg) == (0.0, 0.0, 200.0, 4200.0)


def test_wall_rect_single_face_default_thickness():
    seg = {"orientation": "h", "pos": 0.0, "start": 0.0, "end": 3000.0, "thickness": None, "single": True}
    assert wall_rect_mm(seg) == (0.0, -100.0, 3000.0, 100.0)


def test_wall_rect_missing_fields():
    assert wall_rect_mm({"orientation": "h", "pos": 1.0}) is None
    assert wall_rect_mm({"orientation": "h", "pos": 0.0, "start": 5.0, "end": 5.0}) is None


def test_column_rect_variants():
    assert column_rect_mm({"x": 100.0, "y": 200.0, "source": "circle", "radius": 150.0}) == (
        -50.0, 50.0, 250.0, 350.0
    )
    assert column_rect_mm({"x": 0.0, "y": 0.0, "width": 400.0, "height": 600.0}) == (
        -200.0, -300.0, 200.0, 300.0
    )
    assert column_rect_mm({"block": "_FZH"}) is None  # 无坐标


def test_window_and_door_rect():
    assert window_rect_mm({"x": 1000.0, "y": 500.0, "width": 1200.0, "height": 200.0}) == (
        400.0, 400.0, 1600.0, 600.0
    )
    # 门 0° 沿 X 展开；90° 沿 Y 展开
    r0 = door_rect_mm({"x": 0.0, "y": 0.0, "rotation": 0.0})
    r90 = door_rect_mm({"x": 0.0, "y": 0.0, "rotation": 90.0})
    assert r0[2] - r0[0] == 900.0 and r0[3] - r0[1] == 200.0
    assert r90[2] - r90[0] == 200.0 and r90[3] - r90[1] == 900.0


# ── Hausdorff 口径 ────────────────────────────────────────


def test_hausdorff_identical_rects_zero():
    rects = [(0.0, 0.0, 6000.0, 200.0), (0.0, 4000.0, 6000.0, 4200.0)]
    assert hausdorff_2d(rects, rects) == 0.0


def test_hausdorff_known_offset():
    a = [(0.0, 0.0, 1000.0, 200.0)]
    b = [(0.0, 1.0, 1000.0, 201.0)]  # 整体下移 1mm
    assert hausdorff_2d(a, b) == pytest.approx(1.0, abs=1e-6)


def test_hausdorff_empty_is_inf():
    assert hausdorff_2d([], [(0.0, 0.0, 1.0, 1.0)]) == float("inf")


# ── 5 张合成 T3 平面图 fixture ─────────────────────────────

_T3_LAYERS = ("WALL", "WINDOW", "WINDOW_TEXT", "COLUMN", "AXIS", "STAIR")


def _new_t3_doc():
    ezdxf = _pymupdf_independent_doc()
    doc = ezdxf.new("R2010")
    for name in _T3_LAYERS:
        if name not in doc.layers:
            doc.layers.add(name)
    doc.appids.new("_TCH")
    return doc


def _wall(doc, x1, y1, x2, y2):
    doc.modelspace().add_line((x1, y1), (x2, y2), dxfattribs={"layer": "WALL"})


def _room_shell(doc, x0, y0, x1, y1, t=200.0):
    """双线矩形房间外壳（四面配对墙）。"""
    for y in (y0, y0 + t):
        _wall(doc, x0, y, x1, y)
    for y in (y1 - t, y1):
        _wall(doc, x0, y, x1, y)
    for x in (x0, x0 + t):
        _wall(doc, x, y0, x, y1)
    for x in (x1 - t, x1):
        _wall(doc, x, y0, x, y1)


def _door_block(doc, x, y, rot=0):
    if "$DorLib2D$00000002" not in doc.blocks:
        blk = doc.blocks.new(name="$DorLib2D$00000002")
        blk.add_line((0, 0), (900, 0))
        blk.add_line((0, 0), (0, 900))
    doc.modelspace().add_blockref(
        "$DorLib2D$00000002", (x, y), dxfattribs={"layer": "WINDOW", "rotation": rot}
    )


def _column_block(doc, x, y):
    if "_FZH" not in doc.blocks:
        blk = doc.blocks.new(name="_FZH")
        blk.add_lwpolyline([(0, 0), (400, 0), (400, 400), (0, 400)], close=True)
    doc.modelspace().add_blockref("_FZH", (x, y), dxfattribs={"layer": "COLUMN"})


def _window_block(doc, x, y):
    if "$WINLIB2D$00000001" not in doc.blocks:
        blk = doc.blocks.new(name="$WINLIB2D$00000001")
        blk.add_line((0, 0), (1200, 0))
        blk.add_line((0, 200), (1200, 200))
    doc.modelspace().add_blockref("$WINLIB2D$00000001", (x, y), dxfattribs={"layer": "WINDOW"})


def _plan_1_single_room():
    """单间 6000×4200，200 墙 + 门 + 柱。"""
    doc = _new_t3_doc()
    _room_shell(doc, 0, 0, 6000, 4200)
    _door_block(doc, 3750, 100)
    _column_block(doc, 200, 3800)
    return doc


def _plan_2_two_rooms():
    """两间并排 8000×5000，中隔墙 100 厚。"""
    doc = _new_t3_doc()
    _room_shell(doc, 0, 0, 8000, 5000)
    for x in (4000, 4100):  # 中隔 100 墙
        _wall(doc, x, 200, x, 4800)
    _door_block(doc, 4050, 100, rot=90)
    _window_block(doc, 2000, 4900)
    return doc


def _plan_3_hall_with_columns():
    """大厅 12000×8000，300 外墙 + 双柱。"""
    doc = _new_t3_doc()
    _room_shell(doc, 0, 0, 12000, 8000, t=300.0)
    _column_block(doc, 4000, 4000)
    _column_block(doc, 8000, 4000)
    _door_block(doc, 6000, 150)
    return doc


def _plan_4_windows():
    """带窗墙 9000×6000，两块库窗。"""
    doc = _new_t3_doc()
    _room_shell(doc, 0, 0, 9000, 6000)
    _window_block(doc, 2500, 5900)
    _window_block(doc, 6500, 5900)
    _door_block(doc, 4500, 100)
    return doc


def _plan_5_grid():
    """2×2 房间网格 10000×10000。"""
    doc = _new_t3_doc()
    _room_shell(doc, 0, 0, 10000, 10000)
    for x in (5000, 5200):  # 纵隔
        _wall(doc, x, 200, x, 9800)
    for y in (5000, 5200):  # 横隔
        _wall(doc, 200, y, 9800, y)
    _door_block(doc, 5100, 100)
    _column_block(doc, 200, 9800)
    return doc


FIVE_PLANS = [
    ("plan1_single_room", _plan_1_single_room),
    ("plan2_two_rooms", _plan_2_two_rooms),
    ("plan3_hall_columns", _plan_3_hall_with_columns),
    ("plan4_windows", _plan_4_windows),
    ("plan5_grid", _plan_5_grid),
]


# ── 导出 / 读回 / 验收 ─────────────────────────────────────


def _roundtrip(plan_fn, tmp_path, name):
    """合成图纸 → DrawingParser 解析 → IFC+STEP 导出 → 读回 → Hausdorff。"""
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.ifc_export import export_ifc4, read_wall_rects_ifc
    from src.baa_engine.step_export import export_step, read_wall_rects_step

    dxf_path = tmp_path / f"{name}.dxf"
    plan_fn().saveas(str(dxf_path))

    result = DrawingParser().parse(str(dxf_path))
    t3 = result.t3_components or {}
    walls = [wall_rect_mm(w) for w in t3.get("walls", [])]
    src_rects = [r for r in walls if r]
    assert src_rects, f"{name} 未识别出墙"

    ifc_path = tmp_path / f"{name}.ifc"
    info = export_ifc4(t3, str(ifc_path))
    assert info and os.path.isfile(ifc_path)
    ifc_rects = read_wall_rects_ifc(str(ifc_path))
    assert len(ifc_rects) == len(src_rects)
    d_ifc = hausdorff_2d(src_rects, ifc_rects)

    step_path = tmp_path / f"{name}.step"
    info = export_step(t3, str(step_path))
    assert info and os.path.isfile(step_path)
    step_rects = read_wall_rects_step(str(step_path), len(src_rects))
    assert len(step_rects) == len(src_rects)
    d_step = hausdorff_2d(src_rects, step_rects)

    return {
        "name": name,
        "walls": len(src_rects),
        "counts": info["counts"],
        "hausdorff_ifc_mm": round(d_ifc, 4),
        "hausdorff_step_mm": round(d_step, 4),
    }


@pytest.mark.parametrize("name,plan_fn", FIVE_PLANS)
@IFC_MARK
@STEP_MARK
def test_five_plans_hausdorff(name, plan_fn, tmp_path):
    """验收口径：5 张平面图 IFC/STEP 导出墙足迹 Hausdorff ≤ 2mm。"""
    r = _roundtrip(plan_fn, tmp_path, name)
    assert r["hausdorff_ifc_mm"] <= 2.0, f"IFC {name}: {r['hausdorff_ifc_mm']}mm"
    assert r["hausdorff_step_mm"] <= 2.0, f"STEP {name}: {r['hausdorff_step_mm']}mm"


@IFC_MARK
@STEP_MARK
def test_export_counts_match_components(tmp_path):
    """导出构件计数与 T3 识别结果一致（墙/柱/门/窗全类覆盖）。"""
    r = _roundtrip(_plan_4_windows, tmp_path, "counts_check")
    assert r["counts"]["walls"] == r["walls"]
    assert r["counts"]["windows"] == 2
    assert r["counts"]["doors"] == 1


def test_export_graceful_degrade_no_walls(tmp_path, monkeypatch):
    """无墙构件：两个导出器均返回 None 且不产生文件。"""
    from src.baa_engine import ifc_export, step_export

    out_ifc = tmp_path / "x.ifc"
    out_step = tmp_path / "x.step"
    assert ifc_export.export_ifc4({"walls": []}, str(out_ifc)) is None
    assert step_export.export_step({"walls": []}, str(out_step)) is None
    assert not out_ifc.exists() and not out_step.exists()


# ── E4-T1：弧形墙足迹 ──────────────────────────────────────


def test_wall_arc_rect_mm_basic():
    """弧形墙包含 arc 字段时返回包围矩形。"""
    from src.baa_engine.ifc_export import wall_arc_rect_mm

    wall = {
        "arc": {"cx": 5000.0, "cy": 3000.0, "radius": 2000.0},
        "thickness": 200.0,
    }
    rect = wall_arc_rect_mm(wall)
    assert rect is not None
    assert rect == (2900.0, 900.0, 7100.0, 5100.0)  # cx±r±t/2


def test_wall_arc_rect_missing_fields():
    """缺少圆心或半径时返回 None。"""
    from src.baa_engine.ifc_export import wall_arc_rect_mm

    assert wall_arc_rect_mm({"arc": {"cx": 1.0}}) is None  # 缺 radius
    assert wall_arc_rect_mm({"arc": {}}) is None  # 全缺
    assert wall_arc_rect_mm({"arc": None}) is None  # arc 为 None


def test_wall_arc_rect_non_arc_returns_none():
    """非弧形墙（无 arc 字段）返回 None。"""
    from src.baa_engine.ifc_export import wall_arc_rect_mm

    wall = {"orientation": "h", "pos": 100.0, "start": 0.0, "end": 5000.0}
    assert wall_arc_rect_mm(wall) is None


# ── E4-T1：SI 单位校验 ──────────────────────────────────────


@IFC_MARK
def test_verify_si_units_valid(tmp_path):
    """导出的 IFC 文件应通过 SI 单位校验。"""
    from src.baa_engine.ifc_export import export_ifc4, verify_si_units

    out_path = str(tmp_path / "si_test.ifc")
    components = {
        "walls": [{"orientation": "h", "pos": 200.0, "start": 0.0, "end": 5000.0, "thickness": 200.0}],
        "doors": [],
        "windows": [],
        "columns": [],
    }
    info = export_ifc4(components, out_path)
    assert info is not None

    result = verify_si_units(out_path)
    assert result["valid"] is True
    assert result["linear_unit"] is not None
    assert result["length_unit"] is not None


@IFC_MARK
def test_verify_si_units_errors_on_corrupted(tmp_path):
    """损坏的 IFC 文件应返回 valid=False。"""
    from src.baa_engine.ifc_export import verify_si_units

    bad_path = str(tmp_path / "bad.ifc")
    with open(bad_path, "w") as f:
        f.write("not a valid ifc file\n")

    result = verify_si_units(bad_path)
    assert result["valid"] is False
    assert len(result["errors"]) > 0


# ── E4-T1：开口检测 ──────────────────────────────────────


def test_find_host_wall_for_door_in_wall():
    """门位于墙段范围内时应识别宿主墙。"""
    from src.baa_engine.ifc_export import _find_host_wall, wall_rect_mm

    walls = [
        {"orientation": "h", "pos": 100.0, "start": 0.0, "end": 6000.0, "thickness": 200.0},
    ]
    door = {"x": 3000.0, "y": 100.0, "rotation": 0.0}
    host = _find_host_wall(door, walls)
    assert host is not None
    assert wall_rect_mm(host) is not None


def test_find_host_wall_no_match():
    """门远离所有墙时返回 None。"""
    from src.baa_engine.ifc_export import _find_host_wall

    walls = [
        {"orientation": "h", "pos": 100.0, "start": 0.0, "end": 1000.0, "thickness": 200.0},
    ]
    door = {"x": 5000.0, "y": 100.0, "rotation": 0.0}
    assert _find_host_wall(door, walls) is None


def test_find_host_wall_missing_coords():
    """门缺少坐标时返回 None。"""
    from src.baa_engine.ifc_export import _find_host_wall

    assert _find_host_wall({}, []) is None
    assert _find_host_wall({"x": None, "y": None}, []) is None


# ── E4-T1：STEP 弧形墙 ──────────────────────────────────────


@STEP_MARK
def test_step_export_arc_wall(tmp_path):
    """STEP 导出应支持弧形墙（圆形截面）。"""
    from src.baa_engine.step_export import export_step

    components = {
        "walls": [
            {
                "arc": {"cx": 5000.0, "cy": 3000.0, "radius": 2000.0},
                "thickness": 200.0,
            },
        ],
        "doors": [],
        "windows": [],
        "columns": [],
    }
    out_path = str(tmp_path / "arc_wall.step")
    info = export_step(components, out_path)
    assert info is not None
    assert info["counts"]["walls"] == 1
    assert (tmp_path / "arc_wall.step").exists()
