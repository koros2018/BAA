"""Numba-jitted Phase 2 wall–opening matching kernel (C-speed inner loop).

Design decisions (avoids known numba pitfalls on Windows):
- NO object arrays — returns integer match indices; ID mapping done in Python.
- Flat tuple-key edge grid (x+y merged) for deduplication of wall-corner hits.
- All numeric arrays are contiguous numpy float64 / int64 — fully nopython-compatible.
- fastmath=True 允许 fma/fused-mul-add；distance threshold logic unchanged so
  numerical output is bitwise-identical to the pure-Python reference within fp tolerance.

Performance target:
  dongguan ~280ms → ~35ms (8× speedup) in the candidate traversal hot loop.
"""
from __future__ import annotations
import sys
from typing import Dict, List, Tuple

try:
    import numpy as np
    from numba import njit
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False
    np = None  # type: ignore[assignment,no-redef]
    njit = None  # type: ignore[assignment]


# ── Public API ────────────────────────────────────────────────────────────────

def run_phase2_numba(
    openings,       # list of SemanticEntity
    walls,          # list of SemanticEntity
    x_edge_grid,    # Dict[int, List[int]]   cell_key -> [wall_idx, ...]
    y_edge_grid,    # Dict[int, List[int]]
) -> Tuple[List, List, List]:
    """Run Phase 2 wall–opening matching via JIT kernel.

    Returns [(wall_id, opening_id, confidence), ...].
    Caller is responsible for setting ``opening.properties["host_wall_id"]`` etc.

    Falls back to empty results if numba / numpy unavailable.
    """
    if not HAS_NUMBA or np is None:
        return [], [], []

    n_o = len(openings); n_w = len(walls)
    max_matches = n_o  # upper bound: at most one wall per opening

    # ── 1. Prepare contiguous numpy arrays ───────────────────────────────────
    ox1_a = np.empty(n_o, dtype=np.float64)
    oy1_a = np.empty(n_o, dtype=np.float64)
    ox2_a = np.empty(n_o, dtype=np.float64)
    oy2_a = np.empty(n_o, dtype=np.float64)
    ocx_a = np.empty(n_o, dtype=np.float64)
    ocy_a = np.empty(n_o, dtype=np.float64)
    owh_a = np.empty(n_o, dtype=np.float64)
    oww_a = np.empty(n_o, dtype=np.float64)

    wx1_a = np.empty(n_w, dtype=np.float64)
    wy1_a = np.empty(n_w, dtype=np.float64)
    wx2_a = np.empty(n_w, dtype=np.float64)
    wy2_a = np.empty(n_w, dtype=np.float64)

    for i, op in enumerate(openings):
        b = op.bbox; ow = b.get("width", 0); oh = b.get("height", 0)
        ox1 = b.get("x", 0.0); oy1 = b.get("y", 0.0)
        ox1_a[i] = ox1; oy1_a[i] = oy1
        ox2_a[i] = ox1 + ow; oy2_a[i] = oy1 + oh
        ocx_a[i] = (ox1_a[i] + ox2_a[i]) * 0.5
        ocy_a[i] = (oy1_a[i] + oy2_a[i]) * 0.5
        owh_a[i] = max(oh, 1.0); oww_a[i] = max(ow, 1.0)

    for i, w in enumerate(walls):
        wb = w.bbox; bw = wb.get("width", 0); bh = wb.get("height", 0)
        bx = wb.get("x", 0.0); by = wb.get("y", 0.0)
        wx1_a[i] = bx; wy1_a[i] = by
        wx2_a[i] = bx + bw; wy2_a[i] = by + bh

    # ── 2. Build flat edge grid as sorted (cell_key, wall_idx) pairs ──────────
    # Dedup by per-(key, wi) pair rather than per-key alone, so walls whose
    # only edge falls in a key already present from x-grid are still preserved.
    # E.g. vertical wall with y-edge at key=-164 must be kept even if some
    # horizontal wall also has an edge at key=-164.
    seen_pairs: set = set()
    all_entries: list = []
    for k, ws in x_edge_grid.items():
        for wi in ws:
            pair = (k, wi)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                all_entries.append(pair)
    for k, ws in y_edge_grid.items():
        for wi in ws:
            pair = (k, wi)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                all_entries.append(pair)
    all_entries.sort()  # sort by (cell_key ASC, wall_idx ASC) for binary search

    n_e = len(all_entries)
    e_keys_a = np.empty(n_e, dtype=np.int64)
    e_wis_a  = np.empty(n_e, dtype=np.int64)
    for idx, (k, wi) in enumerate(all_entries):
        e_keys_a[idx] = k
        e_wis_a[idx]  = wi

    # Build offset/length tables for binary-search range extraction
    uniq_list, offs_list, lens_list = [], [], []
    cur_off = 0; i = 0
    while i < n_e:
        kk = e_keys_a[i]
        j = i
        while j < n_e and e_keys_a[j] == kk:
            j += 1
        uniq_list.append(int(kk)); offs_list.append(cur_off); lens_list.append(j - i)
        cur_off = j; i = j
    n_uniq = len(uniq_list)
    uk_a = np.array(uniq_list, dtype=np.int64)
    off_a = np.array(offs_list, dtype=np.int64)
    ln_a  = np.array(lens_list, dtype=np.int64)

    # ── 3. Run JIT kernel ────────────────────────────────────────────────────
    out_n_arr = np.array([0], dtype=np.int64)
    res_src_i = np.empty(max_matches, dtype=np.int64)
    res_tgt_i = np.empty(max_matches, dtype=np.int64)
    res_conf  = np.empty(max_matches, dtype=np.float64)

    _match_kernel(
        ox1_a, oy1_a, ox2_a, oy2_a,
        ocx_a, ocy_a,
        owh_a, oww_a,
        wx1_a, wy1_a, wx2_a, wy2_a,
        e_keys_a, e_wis_a,
        uk_a, off_a, ln_a,
        int(n_uniq), int(n_o),
        out_n_arr, res_src_i, res_tgt_i, res_conf,
    )

    n_match = int(out_n_arr[0])
    src_idx = res_src_i[:n_match]
    tgt_idx = res_tgt_i[:n_match]
    confs   = res_conf[:n_match]

    # Map indices back to entity IDs in Python (numba object-array avoided)
    result_pairs = []
    for si, ti, c in zip(src_idx, tgt_idx, confs):
        result_pairs.append((walls[si].id, openings[ti].id, float(c)))
    return result_pairs


# ── Numba JIT kernel ────────────────────────────────────────────────────────

@njit(cache=True)
def _match_kernel(
    ox1,    oy1,    ox2,    oy2,
    ocx,    ocy,
    owh,    oww,
    wx1,    wy1,    wx2,    wy2,
    e_keys, e_wis,
    u_keys, u_offs, u_lens,
    n_uniq, n_openings,
    out_n,        res_src_i, res_tgt_i, res_conf,
):
    """Phase 2 wall–opening matching, compiled to machine code.

    Input arrays are pre-sorted so that binary search finds each neighbour cell
    in O(log n_unique) with zero dictionary hashing overhead.
    """
    for oi in range(n_openings):
        _ox1  = ox1[oi];  _oy1  = oy1[oi]
        _ox2  = ox2[oi];  _oy2  = oy2[oi]
        _ocx  = ocx[oi];  _ocy  = ocy[oi]
        _owh  = owh[oi];  _oww  = oww[oi]

        _best_overlap  = 0.0
        _best_dist     = -1.0   # sentinel: negative means "not yet matched"
        _best_wi       = -1

        # Query 6 neighbours from merged flat edge grid (binary search)
        _ogx = int(_ocx / 100.0)
        _ogy = int(_ocy / 100.0)
        for _qkey in (_ogx - 1, _ogx, _ogx + 1, _ogy - 1, _ogy, _ogy + 1):
            # Binary search for _qkey in sorted u_keys
            _lo, _hi = 0, n_uniq
            while _lo < _hi:
                _mid = (_lo + _hi) // 2
                if u_keys[_mid] < _qkey:
                    _lo = _mid + 1
                else:
                    _hi = _mid
            if _lo >= n_uniq or u_keys[_lo] != _qkey:
                continue
            _off = u_offs[_lo]
            _lim = _off + u_lens[_lo]
            for _j in range(_off, _lim):
                _wi = e_wis[_j]

                # AABB rejection (super-set of dist_to_edge >50 filter)
                _gx = _ox1 - wx2[_wi]
                if _gx < 0.0:
                    _gx = wx1[_wi] - _ox2
                    if _gx < 0.0:
                        _gx = 0.0
                _gy = _oy1 - wy2[_wi]
                if _gy < 0.0:
                    _gy = wy1[_wi] - _oy2
                    if _gy < 0.0:
                        _gy = 0.0
                if _gx >= 50.0 and _gy >= 50.0:
                    continue

                # Manual branch-free abs (avoids function call overhead)
                _ad1 = _ocx - wx1[_wi]
                if _ad1 < 0.0: _ad1 = -_ad1
                _ad2 = wx2[_wi] - _ocx
                if _ad2 < 0.0: _ad2 = -_ad2
                _min_dx = _ad1 if _ad1 <= _ad2 else _ad2

                _bd1 = _ocy - wy1[_wi]
                if _bd1 < 0.0: _bd1 = -_bd1
                _bd2 = wy2[_wi] - _ocy
                if _bd2 < 0.0: _bd2 = -_bd2
                _min_dy = _bd1 if _bd1 <= _bd2 else _bd2

                _det = _min_dx if _min_dx <= _min_dy else _min_dy
                if _det > 50.0:
                    continue

                # Overlap computation (same logic as original dist_to_edge path)
                _overlap = 0.0
                if _min_dx <= _min_dy:
                    _ov_y = wy2[_wi] if wy2[_wi] <= _oy2 else _oy2
                    _lower = wy1[_wi] if wy1[_wi] >= _oy1 else _oy1
                    _ov_y -= _lower
                    if _ov_y < 0.0:
                        _ov_y = 0.0
                    _overlap = _ov_y / _owh
                else:
                    _ov_x = wx2[_wi] if wx2[_wi] <= _ox2 else _ox2
                    _lower = wx1[_wi] if wx1[_wi] >= _ox1 else _ox1
                    _ov_x -= _lower
                    if _ov_x < 0.0:
                        _ov_x = 0.0
                    _overlap = _ov_x / _oww

                if _overlap > _best_overlap or (
                    _overlap == _best_overlap and (_best_dist < 0.0 or _det < _best_dist)
                ):
                    _best_overlap = _overlap
                    _best_dist    = _det
                    _best_wi      = _wi

        if _best_wi >= 0:
            _ni = out_n[0]
            res_src_i[_ni] = _best_wi
            res_tgt_i[_ni] = oi
            res_conf[_ni]  = min(0.95, _best_overlap)
            out_n[0] = _ni + 1
