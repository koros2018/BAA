"""P84 spike: DXF 闭合多边形直接提取 room/corridor"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ezdxf

ROOT = Path(__file__).resolve().parent.parent
DXF_CANDIDATES = [
    ROOT / "data/drawings/real/A1云计算中心平面图0405_t3.dxf",
    ROOT / "data/drawings/real/东莞通-建筑-外部参照（不打印）.dxf",
    ROOT / "data/drawings/real/A1云计算中心_水消防2017.03.31_t3.dxf",
    ROOT / "data/drawings/real/6.火灾自动报警_（报审）_t3.dxf",
    ROOT / "data/drawings/real/9.气体灭火（唯美图框）_t3.dxf",
]

MIN_AREA = 5    # m²
MAX_AREA = 3000  # m²

def extract_closed_polys(dxf_path):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    polys = []
    for e in msp:
        if e.dxftype() == "LWPOLYLINE" and e.get("closed", 0) == 1:
            pts = [(p[0], p[1]) for p in e.geom_points()]
            if len(pts) < 3:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            area = 0.5 * abs(sum(x1*(y2-y0) for (x0,y0),(x1,y1),(x2,y2) in zip(pts, pts[1:], [pts[0]]+pts[1:-1])))
            polys.append((min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys), area, e.dxf.layer))
        elif e.dxftype() == "CIRCLE":
            r = e.dxf.radius
            if r > 0:
                area = 3.14159 * r * r
                polys.append((e.dxf.center[0]-r, e.dxf.center[1]-r, 2*r, 2*r, area, e.dxf.layer))
    return polys

print(f"{'File':45s} {'Poly':>5s} {'Room':>5s} {'Corr':>5s} {'Area range':>20s} {'Layer samples':40s}")
print("="*125)
for p in DXF_CANDIDATES:
    if not p.exists():
        continue
    try:
        polys = extract_closed_polys(p)
        areas = [p[4] for p in polys]
        room_candidates = [p for p in polys if MIN_AREA < p[4] < MAX_AREA]
        # corridor heuristic: long and narrow (aspect ratio > 3)
        corridor_candidates = [p for p in polys if p[2] > 0 and p[3] > 0 and MIN_AREA < p[4] < MAX_AREA and max(p[2],p[3])/max(min(p[2],p[3]),0.01) > 3]
        ar = f"{min(areas):.0f}-{max(areas):.0f}" if areas else "N/A"
        layers = list(set(p[5] for p in room_candidates[:10]))[:3]
        print(f"{p.name[:44]:45s} {len(polys):5d} {len(room_candidates):5d} {len(corridor_candidates):5d} {ar:>20s} {str(layers):40s}")
    except Exception as e:
        print(f"{p.name[:44]:45s} ERROR: {e}")

print("\n结论: 若 Room 列 > 0 且数量合理，方案可行")