"""
BAA DWG→DXF 手动转换 v3（正确读取ezdwg Entity.dxf字典）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def convert_dwg_safe(dwg_path: str, output_path: str) -> int:
    import ezdwg
    import ezdxf

    doc = ezdwg.read(dwg_path)
    msp_src = doc.modelspace()
    dxf_doc = ezdxf.new("R2010")
    msp_dst = dxf_doc.modelspace()

    total = 0
    for dxf_type in ["LINE", "LWPOLYLINE", "CIRCLE", "ARC", "TEXT"]:
        try:
            entities = list(msp_src.query(types=dxf_type))
        except Exception:
            continue

        for ent in entities:
            try:
                d = ent.dxf
                layer = str(d.get("layer_handle", "0"))
                color = d.get("resolved_color_index", 7) or 7

                if dxf_type == "LINE":
                    msp_dst.add_line(
                        d["start"][:2], d["end"][:2],
                        dxfattribs={"color": color},
                    )
                elif dxf_type == "LWPOLYLINE":
                    pts = [(p[0], p[1]) for p in d["points"]]
                    if len(pts) >= 2:
                        msp_dst.add_lwpolyline(pts, dxfattribs={"color": color})
                elif dxf_type == "CIRCLE":
                    msp_dst.add_circle(
                        (d["center"][0], d["center"][1]), d["radius"],
                        dxfattribs={"color": color},
                    )
                elif dxf_type == "ARC":
                    msp_dst.add_arc(
                        (d["center"][0], d["center"][1]), d["radius"],
                        d["start_angle"], d["end_angle"],
                        dxfattribs={"color": color},
                    )
                elif dxf_type == "TEXT":
                    ins = d.get("insert", (0, 0, 0))
                    msp_dst.add_text(
                        d.get("text", ""),
                        dxfattribs={
                            "color": color,
                            "height": d.get("height", 2.5),
                            "insert": (ins[0], ins[1]),
                        },
                    )
                total += 1
            except Exception:
                pass

    dxf_doc.saveas(output_path)
    return total


def main():
    data_dir = Path(__file__).resolve().parent.parent / "data"
    real_dir = data_dir / "drawings" / "real"
    real_dir.mkdir(parents=True, exist_ok=True)

    # 找到所有DWG
    dwg_files = []
    for ext in ("*.dwg", "*.DWG"):
        dwg_files.extend(data_dir.rglob(ext))
    dwg_files = [f for f in dwg_files if f.stat().st_size > 100 * 1024]

    print(f"📂 找到 {len(dwg_files)} 个DWG文件")
    for f in dwg_files:
        print(f"  {f.relative_to(data_dir)} ({f.stat().st_size/1024/1024:.1f}MB)")

    results = []
    for dwg_path in dwg_files:
        output_name = dwg_path.stem.replace(" ", "_") + ".dxf"
        output_path = real_dir / output_name
        if output_path.exists():
            print(f"\n⏭️  跳过: {output_name}")
            continue

        print(f"\n🔄 {dwg_path.name}")
        try:
            count = convert_dwg_safe(str(dwg_path), str(output_path))
            size_kb = output_path.stat().st_size / 1024 if output_path.exists() else 0
            status = "✅" if count > 50 else "⚠️"
            print(f"  {status} {count}个图元, {size_kb:.0f}KB")
            results.append((output_path, count))
        except Exception as e:
            print(f"  ❌ {str(e)[:80]}")

    print(f"\n{'=' * 50}")
    usable = [(p, c) for p, c in results if c > 50]
    print(f"可用DXF: {len(usable)}张")
    for p, c in usable:
        print(f"  {p.name} ({c}个图元)")


if __name__ == "__main__":
    main()