/**
 * @file _phase2_ext.c
 * @brief Phase 2 wall–opening matching kernel — pure C extension for BAA engine.
 *
 * T-opt29：将 Phase 2 的 dist_to_edge + overlap 候选遍历从 Python/numba
 * 下沉到原生 C，直接通过 PyBuffer protocol 访问 numpy 内存，绕过 byte-code
 * 开销。C 扩展对 numba/kernel 是替代方案；relations.py 优先选 C 路径，失败时
 * fallback 到 numba。
 *
 * ## 算法概要
 *
 * 每个 opening 查询中心点所在 ±1 邻域 edge-cell（共 6 个 key），在
 * e_keys/e_wis flat array 上二分查找，遍历对应墙引用，依次应用：
 *   1. **AABB 前置拒绝**：若轴向间隙 gx >= 50mm 且 gy >= 50mm → 跳过
 *   2. **dist_to_edge**：min(|ocx-wx1|, |ocx-wx2|), min(|ocy-wy1|, |ocy-wy2|)，取
 *      mindx/mindy 较小值，超出 50mm 则跳过
 *   3. **overlap**：按 mindx <= mindy（主导轴）分别算 x/y 方向重叠比例
 *   4. **最佳匹配**：最高 overlap 优先；tie-break 取更小的 det
 *   5. **confidence cap**：ov >= 0.95 → 统一记为 0.95
 *
 * ## ABI 注意事项
 *
 * Windows x64 / Python 3.13 / MSVC 14.x 下 PyArg_ParseTuple("ll", ...)
 * 返回垃圾值（实测 n_op_ll = 140720308486144）。已改用手动
 * PyTuple_GetItem + PyLong_AsLongLong 逐参数解析规避此问题。
 *
 * ## API 签名（Python 侧调用）
 *
 * ```python
 * match_phase2(
 *     ox1, oy1, ox2, oy2,   # float64[O] — opening bbox
 *     ocx, ocy, owh, oww,   # float64[O] — opening cx,cy,height,width
 *     wx1, wy1, wx2, wy2,   # float64[W] — wall bbox
 *     e_keys, e_wis,        # int64[E] — flat edge grid keys & wall indices
 *     uk, uoffs, ulens,     # int64[U] — unique key table + offset+len
 *     n_op, n_uq,           # long long
 *     osrc, otgt, ocf, on_  # output: int64[O], int64[O], float64[O], int64[1]
 * ) -> None
 * ```
 *
 * Output 数组由调用方预先分配，on_[0] 写入实际匹配数；osrc[i]/otgt[i]/ocf[i]
 * 分别记录第 i 条匹配的 wall_idx、opening_idx、confidence。
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>

/* ── Kernel ───────────────────────────────────────────────────────────────── */

/**
 * @brief 单个 opening 的墙体匹配核心循环。
 *
 * 使用传入的直接指针访问 numpy 数据区，避免任何 Python 对象操作。
 *
 * @param ox1..oww   contiguous float64 arrays of length n_openings
 * @param wx1..wy2   contiguous float64 arrays of length n_walls
 * @param e_keys,e_wis  flat edge-grid sorted by cell key, length = total entries
 * @param uk,uoffs,ulens  unique key lookup tables, length = n_uq
 * @param n_uq        number of unique cell keys in uk[]
 * @param oi          index of current opening being processed
 * @param osrc        pre-allocated int64 output buffer — writes wall idx
 * @param otgt        pre-allocated int64 output buffer — writes opening idx (=oi)
 * @param ocf         pre-allocated float64 output buffer — writes confidence
 * @param on          pointer to match counter; incremented after each write
 */
static void run_one(const double* ox1, const double* oy1,
                    const double* ox2, const double* oy2,
                    const double* ocx, const double* ocy,
                    const double* owh, const double* oww,
                    const double* wx1, const double* wy1,
                    const double* wx2, const double* wy2,
                    const int64_t* e_keys, const int64_t* e_wis,
                    const int64_t* uk,  const int64_t* uoffs, const int64_t* ulens,
                    int64_t n_uq,
                    int64_t oi,
                    int64_t* osrc, int64_t* otgt, double* ocf, int64_t* on)
{
    /* Opening scalar fields — hoisted out of inner loops */
    const double _ox1 = ox1[oi], _oy1 = oy1[oi];
    const double _ox2 = ox2[oi], _oy2 = oy2[oi];
    const double _ocx = ocx[oi], _ocy = ocy[oi];
    const double _owh = owh[oi], _oww = oww[oi];

    /* Edge-cell bucket indices (100 mm cells). Using floor semantics via cast
     * is consistent with relations.py which also uses int(x / 100.0). */
    const int64_t ogx = (int64_t)(_ocx / 100.0);
    const int64_t ogy = (int64_t)(_ocy / 100.0);

    /* Best candidate so far */
    double bov = 0.0;       /* best overlap found            */
    double bdist = -1.0;    /* best dist_to_edge (-1 = unset) */
    int64_t bwi = -1;       /* winning wall index             */

    /* Query 6 neighbour cell keys: gx±1 and gy±1 */
    const int64_t qk[6] = {ogx-1, ogx, ogx+1, ogy-1, ogy, ogy+1};
    for (int qi = 0; qi < 6; ++qi) {
        const int64_t key = qk[qi];

        /* Binary search for key in sorted uk[] — O(log n_uq) */
        int64_t lo = 0, hi = n_uq;
        while (lo < hi) {
            const int64_t mid = (lo + hi) >> 1;
            if (uk[mid] < key) lo = mid + 1; else hi = mid;
        }
        if (lo >= n_uq || uk[lo] != key) continue;  /* key not present */

        const int64_t off = uoffs[lo], lim = off + ulens[lo];
        for (int64_t j = off; j < lim; ++j) {
            const int64_t wi = e_wis[j];
            const double cw1 = wx1[wi], cwy1 = wy1[wi];
            const double cw2 = wx2[wi], cwy2 = wy2[wi];

            /* ── Step 1: AABB rejection ─────────────────────────────────── */
            /* Computes axial gap (0 when overlapping) along x and y axes.
             * If both gaps >= 50 mm the opening cannot be within 50 mm of
             * any edge of this wall → safe to skip. This is a strict
             * superset of the dist_to_edge filter below. */
            double gx = _ox1 - cw2;
            if (gx < 0) { gx = cw1 - _ox2; if (gx < 0) gx = 0; }
            double gy = _oy1 - cwy2;
            if (gy < 0) { gy = cwy1 - _oy2; if (gy < 0) gy = 0; }
            if (gx >= 50.0 && gy >= 50.0) continue;

            /* ── Step 2: dist_to_edge ───────────────────────────────────── */
            /* Branch-free abs and min over 4 distances from opening center
             * to the four wall edges. det = min(mindx, mindy) is the
             * Manhattan-projection distance to the nearest wall segment. */
            double ad1 = _ocx - cw1; if (ad1 < 0) ad1 = -ad1;
            double ad2 = cw2 - _ocx; if (ad2 < 0) ad2 = -ad2;
            double mindx = ad1 <= ad2 ? ad1 : ad2;
            double bd1 = _ocy - cwy1; if (bd1 < 0) bd1 = -bd1;
            double bd2 = cwy2 - _ocy; if (bd2 < 0) bd2 = -bd2;
            double mindy = bd1 <= bd2 ? bd1 : bd2;
            const double det = mindx <= mindy ? mindx : mindy;
            if (det > 50.0) continue;  /* too far from all edges */

            /* ── Step 3: overlap ratio ──────────────────────────────────── */
            /* Overlap is measured along the shorter axial direction (the one
             * that achieved det), giving a "projected containment" metric.
             * ov ∈ [0, 1] where 1 means the opening fully covers the wall
             * extent along the dominant axis. */
            double ov = 0.0;
            if (mindx <= mindy) {
                double dy = cwy2 < _oy2 ? cwy2 : _oy2;
                double low = cwy1 > _oy1 ? cwy1 : _oy1;
                dy -= low; if (dy < 0) dy = 0;
                ov = dy / _owh;
            } else {
                double dx = cw2 < _ox2 ? cw2 : _ox2;
                double low = cw1 > _ox1 ? cw1 : _ox1;
                dx -= low; if (dx < 0) dx = 0;
                ov = dx / _oww;
            }

            /* ── Step 4: update best match ──────────────────────────────── */
            /* Tie-break rule: higher overlap wins; equal overlap prefers
             * smaller dist_to_edge. */
            if (ov > bov || (ov == bov && (bdist < 0.0 || det < bdist))) {
                bov = ov; bdist = det; bwi = wi;
            }
        }
    }

    /* Write match if any candidate survived the filters */
    if (bwi >= 0) {
        const int64_t ni = *on;
        osrc[ni] = bwi;           /* wall index           */
        otgt[ni] = oi;            /* opening index        */
        ocf[ni]  = bov < 0.95 ? bov : 0.95; /* confidence capped at 0.95 */
        *on = ni + 1;
    }
}

/* ── Helper: acquire numpy buffer pointer ─────────────────────────────────── */

/**
 * @brief Acquire a simple contiguous buffer from a numpy array object.
 *
 * Calls PyObject_GetBuffer with PyBUF_SIMPLE then immediately releases the
 * buffer. Only validates contiguity; returns a raw void* to the data area.
 *
 * @param obj       Python object (expected: numpy ndarray, float64 or int64)
 * @param out_ptr   [out] receives the raw data pointer
 * @return 0 on success, -1 with exception set on failure
 */
static int acquire_buf(PyObject* obj, void** out_ptr)
{
    Py_buffer vb;
    if (PyObject_GetBuffer(obj, &vb, PyBUF_SIMPLE) != 0) return -1;
    *out_ptr = vb.buf;
    PyBuffer_Release(&vb);
    return 0;
}

/* ── Python entry point ───────────────────────────────────────────────────── */

/**
 * @brief Python callable: match_phase2(...).
 *
 * Accepts exactly 23 positional arguments unpacked from the call tuple using
 * manual PyLong_AsLongLong rather than PyArg_ParseTuple with "ll" format,
 * since the latter produces garbage on Windows x64 / Python 3.13 / MSVC 14.x
 * due to an ABI incompatibility between PyLLong and Microsoft's long long.
 *
 * Input arrays must be contiguous numpy arrays of dtype float64 (coords) or
 * int64 (indices/counts). Output arrays are pre-allocated by the caller.
 *
 * @param self   module object (unused)
 * @param args   PyTuple with 23 elements — see file-level doc for layout
 * @return NULL on error with exception set; otherwise None
 */
static PyObject* py_match(PyObject* self, PyObject* args)
{
    /* Validate argument count upfront — prevents downstream IndexError */
    if (!PyTuple_Check(args) || PyTuple_Size(args) != 23) {
        PyErr_SetString(PyExc_TypeError, "expected 23 arguments");
        return NULL;
    }

    #define TUP_GET(i) PyTuple_GetItem(args, i)

    /* ── Openings: 8 contiguous float64 arrays ─────────────────────────── */
    const double *pd[8];
    for (int i = 0; i < 8; ++i) {
        if (acquire_buf(TUP_GET(i), (void**)&pd[i]) != 0) {
            PyErr_SetString(PyExc_TypeError, "opening array failed");
            return NULL;
        }
    }

    /* ── Walls: 4 contiguous float64 arrays ────────────────────────────── */
    const double *pw[4];
    for (int i = 0; i < 4; ++i) {
        if (acquire_buf(TUP_GET(i + 8), (void**)&pw[i]) != 0) {
            PyErr_SetString(PyExc_TypeError, "wall array failed");
            return NULL;
        }
    }

    /* ── Edge grid: 5 contiguous int64 arrays ──────────────────────────── */
    const int64_t *pe[5];
    for (int i = 0; i < 5; ++i) {
        if (acquire_buf(TUP_GET(i + 12), (void**)&pe[i]) != 0) {
            PyErr_SetString(PyExc_TypeError, "edge array failed");
            return NULL;
        }
    }

    /* ── Scalar counts ─────────────────────────────────────────────────── */
    long long n_op_ll = PyLong_AsLongLong(TUP_GET(17));
    long long n_uq_ll = PyLong_AsLongLong(TUP_GET(18));
    if (n_op_ll < 0 || n_uq_ll < 0) {
        PyErr_SetString(PyExc_ValueError, "n_op/n_uq must be non-negative");
        return NULL;
    }

    /* ── Output buffers: 4 pre-allocated arrays ────────────────────────── */
    void *pv[4];
    for (int i = 0; i < 4; ++i) {
        if (acquire_buf(TUP_GET(i + 19), &pv[i]) != 0) {
            PyErr_SetString(PyExc_TypeError, "output array failed");
            return NULL;
        }
    }

    int64_t* po_s = (int64_t*)pv[0];   /* source wall indices   */
    int64_t* po_t = (int64_t*)pv[1];   /* target opening indices*/
    double*  po_c = (double*)  pv[2];  /* confidence scores     */
    int64_t* po_n = (int64_t*)pv[3];   /* match counter         */

    *po_n = 0;
    for (long long i = 0; i < n_op_ll; ++i) {
        run_one(pd[0], pd[1], pd[2], pd[3], pd[4], pd[5], pd[6], pd[7],
                pw[0], pw[1], pw[2], pw[3],
                pe[0], pe[1], pe[2], pe[3], pe[4],
                n_uq_ll, i, po_s, po_t, po_c, po_n);
    }
    Py_RETURN_NONE;
}

#undef TUP_GET

/* ── Module definition ────────────────────────────────────────────────────── */

static PyMethodDef meths[] = {
    {"match_phase2", (PyCFunction)py_match, METH_VARARGS,
     "match_phase2(oa..., wa..., ek..., ll, oa_out...) -> None\n\n"
     "Phase 2 wall–opening matching kernel.\n"
     "See module docstring for full signature."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moddef = {
    PyModuleDef_HEAD_INIT, "phase2_match",
    "Pure-C Phase 2 wall-opening matching kernel (T-opt29).\n\n"
    "Call: match_phase2(ox1..oww, wx1..wy2, "
    "e_keys,e_wis, uk,uoffs,ulens, n_op, n_uq, osrc,otgt,ocf,on_)\n"
    "All input arrays must be contiguous numpy arrays (float64 for coords, "
    "int64 for indices/counters). Output arrays are pre-allocated by the "
    "caller and written in-place.",
    -1, meths
};

PyMODINIT_FUNC PyInit_phase2_match(void)
{
    return PyModule_Create(&moddef);
}
