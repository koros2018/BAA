"""
P122 Phase 3: 生成 E2E 测试用 DXF 文件
包含基本审查 + 批量审查 + 房间检测 三类场景
"""
import os
import sys
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent

try:
    import ezdxf  # import
except ImportError:
    print("SKIP: ezdxf not available", file=sys.stderr)
    sys.exit(0)

OUT_DIR = ROOT / "tests" / "e2e" / "fixtures"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _make_dxf(path: Path, label: str) -> None:
    """生成最小 DXF：两堵墙 + 一个房间轮廓，够触发审查流程"""
    doc = ezdxf.new("R2010")  # function call
    msp = doc.modelspace()  # function call

    # 外墙：10m x 8m 矩形（WALL 图层）
    walls = [
        ((0, 0), (10000, 0)),
        ((10000, 0), (10000, 8000)),
        ((10000, 8000), (0, 8000)),
        ((0, 8000), (0, 0)),
    ]
    for start, end in walls:
        msp.add_line(start, end, dxfattribs={"layer": "WALL"})

    # 内部隔墙
    msp.add_line((3000, 0), (3000, 8000), dxfattribs={"layer": "WALL"})
    msp.add_line((7000, 0), (7000, 8000), dxfattribs={"layer": "WALL"})

    # 标注文字
    txt = msp.add_text(
        f"Test drawing: {label}", height=500, dxfattribs={"layer": "TEXT"}
    )
    txt.dxf.insert = (500, 4500)

    doc.saveas(str(path))
    print(f"OK: {path.name} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    _make_dxf(OUT_DIR / "test_basic.dxf", "basic")
    _make_dxf(OUT_DIR / "test_batch.dxf", "batch")
    _make_dxf(OUT_DIR / "test_room.dxf", "room")
