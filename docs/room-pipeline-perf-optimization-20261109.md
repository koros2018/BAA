# 扫线法房间管线性能优化：空间网格索引（2026-11-09）

> **背景**：Heavy DWG（约 36 分钟）性能定位显示主因在 `_split_t_junctions`
> 和 `_build_planar_graph` 的 O(n²) 全量两两比较。本次用空间网格索引
> 将两者降为 O(n·k)，房间管线整体提速约 15 倍。
>
> 口径：真实图纸 `data/drawings/real` + `data/files/*.dxf`。临时脚本用完即删。

---

## 1. 性能定位

| 函数 | 复杂度 | 瓶颈原因 |
|------|--------|---------|
| `_split_t_junctions` Pass 1 | O(n²) | 每条线段扫描所有线段检查端点投影 |
| `_split_t_junctions` Pass 2 | O(n²) | 所有线段对做真交叉检测 |
| `_build_planar_graph._find_or_create` | O(n²) | 每个端点线性扫描所有已有节点找最近 |
| `_merge_collinear` | O(n²) | 每个 coord 线性扫描已有簇锚点 |

实测（dongguan，2791 段）：

| 函数 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| `_split_t_junctions` | 7.65s | 1.79s | 4.3x |
| `_build_planar_graph` | 21.48s | 0.12s | 173x |
| **房间管线合计** | **29.1s** | **1.9s** | **15x** |

---

## 2. 空间网格索引设计

新增 `_SpatialGrid` 类（[room.py L1310-L1420](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/room.py#L1310-L1420)）。

### 2.1 核心参数

- `cell_size = _MATCH_THRESHOLD = 100mm`（匹配阈值）
- 保证任意距离 ≤100mm 的点对必落在相邻 cell（含自身）内

### 2.2 线段插入（`insert_segment`）

沿线段按 `cell_size/2 = 50mm` 步长采样，每个采样点插入其 cell。

**为什么步长取 cell_size/2**：合并后的墙线可达数万 mm（跨数百 cell）。
若按 bbox 插入会爆炸（超长线段插入海量 cell）或漏插（只插中心 cell 导致
漏检）。按路径采样保证：若线段 j 与查询 bbox 相交，则 j 的某个采样点落在
相交区域，从而 j 被插入该区域所在 cell，查询时能被正确找到。

**为什么步长不能是 cell_size**：采样点间隔 cell_size 可能恰好跳过某些
cell（斜线穿过 cell 角），导致漏检。取 cell_size/2 保证任意两个相邻采样点
距离 ≤ cell_size/2，不会跳过任何被线段穿过的 cell。

### 2.3 查询（`query_bbox`）

额外扩张 1 个 cell（cell_size）容差：因为采样点间隔 cell_size/2，线段与
查询 bbox 相交时其采样点可能落在 bbox 边界外最多 1 个 cell，需额外容差
避免漏检。

---

## 3. 功能等价性验证

**关键**：空间索引必须与原始 O(n²) 全量扫描**严格等价**，否则会改变房间
识别结果（漏检/误检）。

### 3.1 逐函数等价性

- `_split_t_junctions`：villa/stadion 完全一致；dongguan 有 21 个坐标
  差异（浮点精度导致的分割点位置舍入，<1mm 级），**不影响最终房间数**。
- `_build_planar_graph`：villa/stadion/dongguan 节点数、边数完全一致。
- `_merge_collinear`：**不优化**。其「按插入顺序找第一个匹配簇」语义依赖
  插入顺序，无法用排序/二分严格等价（随机 5000 组测试发现 40 组不匹配）。
  保留原始 O(n²) 实现。

### 3.2 最终房间数对比（真实图纸）

| 图纸 | 优化前 | 优化后 | 一致 |
|------|--------|--------|------|
| villa | 22 | 22 | ✅ |
| stadion | 46 | 46 | ✅ |
| dongguan | 186 | 186 | ✅ |

---

## 4. 测试

- 专项测试：89 passed, 11 skipped（room integrity + pdf pipeline + p121 classifier）
- 全量测试：待跑（见 §6）

---

## 5. 代码改动

文件：[room.py](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/room.py)

| 位置 | 变更 |
|------|------|
| L1310-1420 | 新增 `_SpatialGrid` 类（insert_segment / query_point / query_bbox） |
| L1421-1440 | `_split_t_junctions` 用空间索引替代全量双重循环 |
| L1518-1550 | `_build_planar_graph._find_or_create` 用空间索引查最近节点 |

---

## 6. 待观察项

- **DWG 解析本身**（`_parse_dwg` → `_try_ezdwg_direct`）仍是独立瓶颈，
  与房间管线无关。Heavy DWG 的 36 分钟中，房间管线只占约 29 秒（dongguan），
  其余时间在 DWG 转换/解析。已由 [dwg-dxf-cache-optimization-20261109.md](file:///d:/OpenClawData/BAA/docs/dwg-dxf-cache-optimization-20261109.md) 处理。
- **`_merge_collinear` 未优化**：dongguan 的 `_axis_align_merge` 仍为 O(n²)。
  若后续成为瓶颈，需设计保持插入顺序语义的优化（如维护锚点链表 + 哈希）。

---

## 7. 后续优化：grid_pattern 门洞/文字邻接空间索引（2026-11-09）

> 独立提交 `6cf8566`，与 §2-§5 的空间网格索引同源但独立落地。

### 7.1 背景

`_detect_grid_pattern_suppressions` 的 `_has_adjacent_context` 对每个候选
房间遍历全部 doors/texts（O(n·m)）。dongguan 177 候选 × 474 实体，
耗时 4.76s，占 `_suppress_implausible_rooms`（6.6s）的 72%。

### 7.2 优化

预构建空间索引：
- **doors** 按 bbox 对角线路径插入（`insert_segment`，覆盖其跨度）
- **texts** 按中心点插入（`insert_point`）
- `_has_adjacent_context` 用 `query_bbox`/`query_point` 查房间邻域候选，
  再精确双轴重叠/距离判断

### 7.3 功能等价性

五图 grid_pattern 数量完全一致：stadion 19 / dongguan 12 / villa 3 /
plans 0 / mosque 0（均不变）。

### 7.4 性能提升（dongguan）

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| `_suppress_implausible_rooms` | 6.6s | 2.53s |
| 完整 analyze | 14.94s | 10.64s |

### 7.5 剩余热点

- `_split_t_junctions` 3.2s（query_bbox 2.3s）
- `_find_faces` 1.1s
- `_build_relations` 1.0s
