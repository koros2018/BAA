"""生成 3D 属性验证用合成 DXF（2026-11-16）。

验证 DIM-011/085/098（净高）与 DIM-031/086（转弯半径）的 handler 语义错配修复：
- synth_3d_clear_height.dxf：消防车道 + 「净高4.5m」标注 → DIM-011/085/098 PASS
- synth_3d_turning_radius.dxf：消防车道 + 「转弯半径12m」标注 → DIM-031/086 PASS

模板参照 scripts/gen_e2e_dxf.py（ezdxf 构造 DXF）。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "drawings" / "real" / "synth"
OUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    import ezdxf
except ImportError:
    print("SKIP: ezdxf not available", file=sys.stderr)
    sys.exit(0)


def _make_clear_height_dxf(path: Path) -> None:
    """消防车道（闭合多边形）+ 净高 4.5m 标注（DIM-011/085/098 验证）。"""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    # 消防车道：闭合多边形 20m × 4m（FIRE_LANE 图层），闭合使 bbox 短边=4000mm
    lane = [(0, 0), (20000, 0), (20000, 4000), (0, 4000)]
    msp.add_lwpolyline(lane, close=True, dxfattribs={"layer": "FIRE_LANE"})
    # 净高标注：4.5m（TEXT 图层，就近车道中心）
    t = msp.add_text("净高4.5m", height=300, dxfattribs={"layer": "TEXT"})
    t.dxf.insert = (1000, 2000)
    doc.saveas(str(path))
    print(f"OK: {path.name} ({path.stat().st_size} bytes)")


def _make_turning_radius_dxf(path: Path) -> None:
    """消防车道（闭合多边形）+ 转弯半径 12m 标注（DIM-031/086 验证）。"""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    # 消防车道：闭合多边形 20m × 4m（FIRE_LANE 图层）
    lane = [(0, 0), (20000, 0), (20000, 4000), (0, 4000)]
    msp.add_lwpolyline(lane, close=True, dxfattribs={"layer": "FIRE_LANE"})
    # 转弯半径标注：12m（TEXT 图层，就近车道中心）
    t = msp.add_text("转弯半径12m", height=300, dxfattribs={"layer": "TEXT"})
    t.dxf.insert = (1000, 2000)
    doc.saveas(str(path))
    print(f"OK: {path.name} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    _make_clear_height_dxf(OUT_DIR / "synth_3d_clear_height.dxf")
    _make_turning_radius_dxf(OUT_DIR / "synth_3d_turning_radius.dxf")
