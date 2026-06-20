#!/usr/bin/env python3
"""
BAA 合成图纸生成工具
生成500张合成DXF图纸用于训练和测试
"""
import ezdxf
from ezdxf.math import Vec2
from pathlib import Path
import random
import os


OUTPUT_DIR = Path(os.path.dirname(__file__)) / ".." / "data" / "drawings" / "synthetic"


def generate_single_drawing(dwg_id: int, width: float, height: float) -> str:
    """生成单张合成图纸"""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # 外墙
    msp.add_lwpolyline([
        (0, 0), (width, 0), (width, height), (0, height), (0, 0)
    ], dxfattribs={"layer": "WALL"})

    # 内墙（随机）
    wall_count = random.randint(2, 5)
    for _ in range(wall_count):
        x = random.uniform(width * 0.1, width * 0.9)
        y = random.uniform(height * 0.1, height * 0.9)
        w = random.uniform(width * 0.05, width * 0.3)
        h = random.uniform(height * 0.05, height * 0.3)
        if random.random() > 0.5:
            # 水平墙
            msp.add_line((x, y), (x + w, y), dxfattribs={"layer": "WALL"})
        else:
            # 垂直墙
            msp.add_line((x, y), (x, y + h), dxfattribs={"layer": "WALL"})

    # 门（随机）
    door_count = random.randint(1, 4)
    for i in range(door_count):
        x = random.uniform(width * 0.1, width * 0.9)
        y = random.uniform(height * 0.1, height * 0.9)
        door_w = random.uniform(0.8, 1.5)
        msp.add_circle((x, y), door_w / 2, dxfattribs={"layer": "DOOR"})

        # 随机部分门为防火门
        if random.random() > 0.7:
            msp.add_text("FD", height=0.3, dxfattribs={
                "layer": "FIRE_DOOR", "insert": (x, y + 0.5)
            })

    # 窗（随机）
    window_count = random.randint(1, 3)
    for _ in range(window_count):
        x = random.uniform(width * 0.1, width * 0.9)
        y = random.uniform(height * 0.1, height * 0.9)
        win_w = random.uniform(1.0, 2.0)
        msp.add_line((x, y), (x + win_w, y), dxfattribs={"layer": "WINDOW"})

    # 楼梯（随机，约50%概率）
    if random.random() > 0.5:
        sx = random.uniform(width * 0.1, width * 0.8)
        sy = random.uniform(height * 0.1, height * 0.8)
        stair_w = random.uniform(1.0, 3.0)
        stair_h = random.uniform(2.0, 5.0)
        msp.add_lwpolyline([
            (sx, sy), (sx + stair_w, sy), (sx + stair_w, sy + stair_h),
            (sx, sy + stair_h), (sx, sy)
        ], dxfattribs={"layer": "STAIR"})

    # 标注（尺寸）- 用简单文本代替
    msp.add_text(f"W={width:.0f} H={height:.0f}", height=0.3, dxfattribs={
        "layer": "DIM", "insert": (0, -1)
    })

    # 安全出口（约30%概率）
    if random.random() > 0.7:
        ex, ey = width - 1, height - 1
        msp.add_text("安全出口", height=0.3, dxfattribs={
            "layer": "EXIT", "insert": (ex, ey)
        })
        msp.add_circle((ex + 1, ey + 1), 0.5, dxfattribs={"layer": "EXIT"})

    # 保存
    filename = f"drawing_{dwg_id:04d}.dxf"
    filepath = OUTPUT_DIR / filename
    doc.saveas(str(filepath))
    return str(filepath)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    total = 500
    print(f"生成 {total} 张合成图纸...")

    for i in range(total):
        width = random.uniform(10, 50)
        height = random.uniform(10, 40)
        filepath = generate_single_drawing(i + 1, width, height)

        if (i + 1) % 50 == 0:
            print(f"  已生成 {i + 1}/{total}")

    print(f"✅ 完成！合成图纸目录: {OUTPUT_DIR}")
    print(f"   总计: {total} 张")


if __name__ == "__main__":
    main()