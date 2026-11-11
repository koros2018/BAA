# -*- coding: utf-8 -*-
"""基准测试：phase2_match C 扩展 vs Numba JIT vs 纯 Python。

测量维度：
  · matches         — 输出关系数（用于验证等价性）
  · c_ms / numba_ms / py_ms — 各实现耗时中位数（ms）
  · speedup         — C/Numba、C/Python 加速比

用法：
  python scripts/bench_phase2_c_ext.py [--sizes small medium large all] \\
                                       [--runs N] [--seed SEED]

默认运行三档规模，每档 5 次取中位数。
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

try:
    from src.baa_engine.semantic_analyzer.phase2_match import match_phase2
    HAS_C = True
except ImportError:
    HAS_C = False

try:
    from src.baa_engine.semantic_analyzer.phase2_kernel import run_phase2_numba
    HAS_NUMBA = run_phase2_numba is not None
except Exception:
    run_phase2_numba = None
    HAS_NUMBA = False

# ── 数据生成 ─────────────────────────────────────────────────────────────────

def _gen_data(n_op: int, n_w: int, seed: int = 42) -> dict:
    """生成 opening/wall bbox 并构建所有所需数组。"""
    rng = np.random.default_rng(seed)
    GRID = 200.0
    WALL_THICK = 10.0

    # 网格墙（横 + 纵交替）
    rows = max(1, n_w // 4)
    cols = max(1, n_w // 2)
    walls_bbox: List[Tuple[float, float, float, float]] = []
    for r in range(rows):
        y = float(r * GRID)
        walls_bbox.append((0.0, y, float(cols * GRID), WALL_THICK))
    for c in range(cols):
        x = float(c * GRID)
        walls_bbox.append((x, 0.0, WALL_THICK, float(rows * GRID)))
    walls_bbox = walls_bbox[:n_w]

    # Opening 随机放置（中心在 wall 附近以保证 dist_to_edge <= 50mm）
    ops_bbox: List[Tuple[float, float, float, float]] = []
    for _ in range(n_op):
        wi = int(rng.integers(0, max(1, len(walls_bbox))))
        wx1, wy1, ww, wh = walls_bbox[wi % max(1, len(walls_bbox))]
        cx = float(rng.uniform(wx1, wx1 + ww))
        cy = float(rng.uniform(wy1, wy1 + wh))
        ow = float(rng.uniform(20.0, 60.0))
        oh = float(rng.uniform(20.0, 60.0))
        ops_bbox.append((cx - ow / 2, cy - oh / 2, ow, oh))

    return _build_arrays(ops_bbox, walls_bbox)


def _build_arrays(ops_bbox, walls_bbox):
    """将 bbox 列表转为 C/numpy/numba/reference 所需的统一数据结构。"""
    n_op = len(ops_bbox); n_w = len(walls_bbox)

    ox1 = np.empty(n_op, dtype=np.float64)
    oy1 = np.empty(n_op, dtype=np.float64)
    ox2 = np.empty(n_op, dtype=np.float64)
    oy2 = np.empty(n_op, dtype=np.float64)
    ocx = np.empty(n_op, dtype=np.float64)
    ocy = np.empty(n_op, dtype=np.float64)
    owh = np.empty(n_op, dtype=np.float64)
    oww = np.empty(n_op, dtype=np.float64)
    for i, (x, y, w, h) in enumerate(ops_bbox):
        ox1[i] = x; oy1[i] = y
        ox2[i] = x + w; oy2[i] = y + h
        ocx[i] = (x + x + w) * 0.5
        ocy[i] = (y + y + h) * 0.5
        owh[i] = max(h, 1.0); oww[i] = max(w, 1.0)

    wx1 = np.fromiter((b[0] for b in walls_bbox), dtype=np.float64, count=n_w)
    wy1 = np.fromiter((b[1] for b in walls_bbox), dtype=np.float64, count=n_w)
    wx2 = np.fromiter((b[0] + b[2] for b in walls_bbox), dtype=np.float64, count=n_w)
    wy2 = np.fromiter((b[1] + b[3] for b in walls_bbox), dtype=np.float64, count=n_w)

    # Flat edge grid
    EDGE_CELL = 100.0
    xg: Dict[int, List[int]] = {}
    yg: Dict[int, List[int]] = {}
    for wi, (x, y, w, h) in enumerate(walls_bbox):
        xg.setdefault(math.floor(x / EDGE_CELL), []).append(wi)
        xg.setdefault(math.floor((x + w) / EDGE_CELL), []).append(wi)
        yg.setdefault(math.floor(y / EDGE_CELL), []).append(wi)
        yg.setdefault(math.floor((y + h) / EDGE_CELL), []).append(wi)

    entries = []
    seen = set()
    for k, ws in xg.items():
        for wi in ws:
            p = (k, wi)
            if p not in seen:
                seen.add(p); entries.append(p)
    for k, ws in yg.items():
        for wi in ws:
            p = (k, wi)
            if p not in seen:
                seen.add(p); entries.append(p)
    entries.sort()

    e_keys = np.array([k for k, _ in entries], dtype=np.int64)
    e_wis  = np.array([wi for _, wi in entries], dtype=np.int64)

    uniq, offs, lens = [], [], []
    cur = 0; i = 0
    while i < len(entries):
        kk = entries[i][0]; j = i
        while j < len(entries) and entries[j][0] == kk:
            j += 1
        uniq.append(int(kk)); offs.append(cur); lens.append(j - i)
        cur = j; i = j

    uk     = np.array(uniq, dtype=np.int64)
    off_a  = np.array(offs, dtype=np.int64)
    ln_a   = np.array(lens, dtype=np.int64)

    cap = n_op
    osrc = np.empty(cap, dtype=np.int64)
    otgt = np.empty(cap, dtype=np.int64)
    ocf  = np.empty(cap, dtype=np.float64)
    on_  = np.array([0], dtype=np.int64)

    from src.baa_engine.semantic_analyzer.models import SemanticEntity
    wall_e = [SemanticEntity(f"W{i}", "wall",
                             {"x": b[0], "y": b[1], "width": b[2], "height": b[3]}, {})
              for i, b in enumerate(walls_bbox)]
    op_e   = [SemanticEntity(f"O{i}", "opening",
                             {"x": b[0], "y": b[1], "width": b[2], "height": b[3]}, {})
              for i, b in enumerate(ops_bbox)]

    return {
        "c_args":      (ox1, oy1, ox2, oy2, ocx, ocy, owh, oww,
                        wx1, wy1, wx2, wy2,
                        e_keys, e_wis, uk, off_a, ln_a,
                        int(n_op), int(len(uniq)),
                        osrc, otgt, ocf, on_),
        "entities":    (op_e, wall_e),
        "grids":       (xg, yg),
        "ops_bbox":    ops_bbox,
        "walls_bbox":  walls_bbox,
        "n_op":        n_op,
        "n_w":         n_w,
    }


# ── 计时工具 ──────────────────────────────────────────────────────────────────

def _warmup(fn, *args, n: int = 3):
    for _ in range(n):
        fn(*args)


def _bench(fn, *args, runs: int = 5) -> Tuple[float, float]:
    """返回 (平均 ms, 中位数 ms)。"""
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn(*args)
        times.append((time.perf_counter() - t0) * 1000)
    s = sorted(times)
    return sum(s) / len(s), s[len(s) // 2]


def _count(on_: np.ndarray) -> int:
    return int(on_[0])


# ── 各实现入口 ────────────────────────────────────────────────────────────────

def _run_c(data: dict) -> int:
    c = data["c_args"]
    on_ = c[-1]
    on_[0] = 0
    match_phase2(*c)
    return _count(on_)


def _run_numba(data: dict) -> int:
    op_e, wall_e = data["entities"]
    xg, yg = data["grids"]
    result = run_phase2_numba(op_e, wall_e, xg, yg)
    return len(result)


def _run_py(data: dict) -> int:
    """纯 Python reference（含 grid 构建）。"""
    ops_bbox = data["ops_bbox"]
    walls_bbox = data["walls_bbox"]

    # 预建 edge grid（与 C/numba 一致）
    EDGE_CELL = 100.0
    xg: Dict[int, List[int]] = {}
    yg: Dict[int, List[int]] = {}
    for wi, (x, y, w, h) in enumerate(walls_bbox):
        xg.setdefault(math.floor(x / EDGE_CELL), []).append(wi)
        xg.setdefault(math.floor((x + w) / EDGE_CELL), []).append(wi)
        yg.setdefault(math.floor(y / EDGE_CELL), []).append(wi)
        yg.setdefault(math.floor((y + h) / EDGE_CELL), []).append(wi)

    matched = 0
    for oi, (ox1, oy1, ow, oh) in enumerate(ops_bbox):
        ox2 = ox1 + ow; oy2 = oy1 + oh
        ocx_v = (ox1 + ox2) * 0.5; ocy_v = (oy1 + oy2) * 0.5
        bov = 0.0; bdist = -1.0; bwi = -1
        ogx = math.floor(ocx_v / 100.0); ogy = math.floor(ocy_v / 100.0)
        qk = [ogx - 1, ogx, ogx + 1, ogy - 1, ogy, ogy + 1]
        for key in qk:
            ws = set(xg.get(key, [])) | set(yg.get(key, []))
            for wi in ws:
                wx1, wy1, ww, wh = walls_bbox[wi]
                wx2 = wx1 + ww; wy2 = wy1 + wh
                gx = ox1 - wx2
                if gx < 0:
                    gx = wx1 - ox2
                    if gx < 0:
                        gx = 0
                gy = oy1 - wy2
                if gy < 0:
                    gy = wy1 - oy2
                    if gy < 0:
                        gy = 0
                if gx >= 50.0 and gy >= 50.0:
                    continue
                ad1 = abs(ocx_v - wx1); ad2 = abs(wx2 - ocx_v)
                mindx = min(ad1, ad2)
                bd1 = abs(ocy_v - wy1); bd2 = abs(wy2 - ocy_v)
                mindy = min(bd1, bd2)
                det = min(mindx, mindy)
                if det > 50.0:
                    continue
                if mindx <= mindy:
                    dy = min(wy2, oy2) - max(wy1, oy1)
                    ov = max(dy, 0.0) / max(oh, 1.0)
                else:
                    dx = min(wx2, ox2) - max(wx1, ox1)
                    ov = max(dx, 0.0) / max(ow, 1.0)
                if ov > bov or (ov == bov and (bdist < 0.0 or det < bdist)):
                    bov = ov; bdist = det; bwi = wi
        if bwi >= 0:
            matched += 1
    return matched


# ── 主流程 ────────────────────────────────────────────────────────────────────

_SIZES = {
    "small":  (50,   150),
    "medium": (500,  1500),
    "large":  (2000, 6000),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2 C 扩展基准测试")
    parser.add_argument("--sizes", nargs="+", default=["small", "medium", "large"],
                        choices=list(_SIZES.keys()) + ["all"],
                        help="测试规模")
    parser.add_argument("--runs", type=int, default=5, help="每档运行次数（取中位数）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    size_names = args.sizes
    if "all" in size_names:
        size_names = list(_SIZES.keys())

    sep = "=" * 80
    print(sep)
    print("  phase2_match C 扩展基准测试  (T-opt29)")
    print(f"  runs={args.runs}  seed={args.seed}")
    print(sep)
    hdr = f"{'规模':<8} {'Op×W':<10} {'matches':<8} " \
          f"{'C(ms)':<10} {'Numba(ms)':<12} {'Py(ms)':<10} " \
          f"{'C/Numba':<10} {'C/Py':<8}"
    print(hdr)
    print("-" * 80)

    results: List[dict] = []
    for name in size_names:
        n_op, n_w = _SIZES[name]
        data = _gen_data(n_op, n_w, seed=args.seed)

        # Warmup
        if HAS_C:
            _warmup(_run_c, data, n=2)
        if HAS_NUMBA:
            _warmup(_run_numba, data, n=2)
        _warmup(_run_py, data, n=1)

        runs = args.runs
        t_c      = _bench(lambda d: _run_c(d),      data, runs=runs) if HAS_C      else (None, None)
        t_numba  = _bench(lambda d: _run_numba(d),  data, runs=runs) if HAS_NUMBA  else (None, None)
        t_py     = _bench(lambda d: _run_py(d),     data, runs=max(1, runs // 2))

        m_c      = _run_c(data)
        m_numba  = _run_numba(data) if HAS_NUMBA else -1
        m_py     = _run_py(data)

        def fmt(t):
            return f"{t[1]:.2f}" if t[0] is not None else "n/a"

        ratio_cn = f"{t_numba[1]/t_c[1]:.2f}x" if HAS_C and HAS_NUMBA and t_c[1] and t_numba[1] else "—"
        ratio_cp = f"{t_py[1]/t_c[1]:.2f}x"  if HAS_C and t_c[1] and t_py[1]   else "—"

        print(f"{name:<8} {n_op:>4}×{n_w:<5} {m_c:<8} "
              f"{fmt(t_c):<10} {fmt(t_numba):<12} {fmt(t_py):<10} "
              f"{ratio_cn:<10} {ratio_cp:<8}")

        results.append({
            "size": name, "n_op": n_op, "n_w": n_w,
            "c_ms": t_c[1], "numba_ms": t_numba[1], "py_ms": t_py[1],
            "matches_c": m_c, "matches_numba": m_numba, "matches_py": m_py,
        })

    print("-" * 80)
    print()

    # Summary
    print("=== 汇总 ===")
    for r in results:
        print(f"  {r['size']:>8}: Op={r['n_op']:>5}  W={r['n_w']:>5}  "
              f"C={r['c_ms']:.2f}ms  "
              f"Numba={r['numba_ms']:.2f}ms  "
              f"Py={r['py_ms']:.2f}ms"
              f"  |  matches C={r['matches_c']} Numba={r['matches_numba']} Py={r['matches_py']}")
        if r['numba_ms'] and r['c_ms']:
            print(f"             C/Numba 加速: {r['numba_ms']/r['c_ms']:.2f}x")
        if r['py_ms'] and r['c_ms']:
            print(f"             C/Python 加速: {r['py_ms']/r['c_ms']:.2f}x")

    # Equivalence check
    all_c = {r['matches_c'] for r in results if r['matches_c'] is not None}
    all_n = {r['matches_numba'] for r in results if r['matches_numba'] is not None}
    all_p = {r['matches_py']     for r in results if r['matches_py']     is not None}
    common = all_c & all_n & all_p
    if common:
        print(f"\n✓ 所有档位 matches 一致: {sorted(common)}")
    else:
        print(f"\n⚠ matches 不一致: C={sorted(all_c)} Numba={sorted(all_n)} Py={sorted(all_p)}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
