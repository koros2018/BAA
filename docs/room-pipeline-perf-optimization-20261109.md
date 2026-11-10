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

> **后续优化（`535094c`）**：采样法对斜线会重复插入同一 cell，dongguan
> 2791 段产生 516714 个 cell entries。改用 Amanatides-Woo DDA 网格遍历
> （从起点 cell 沿线段方向逐步跨越 cell 边界），精确遍历每个 cell 不重
> 不漏，entries 减半至 260324，`_split_t_junctions` 0.853s → 0.635s。

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

---

## 8. 后续优化：查询合并 + _bbox_iou 微优化（2026-11-09）

> 独立提交 `3b7049c`（查询合并）+ `95a0fac`（_bbox_iou）。

### 8.1 查询合并（`3b7049c`）

`_split_t_junctions` 的 Pass 1（端点投影）和 Pass 2（线段真交叉）各自调用
`query_bbox`，对同一条线段 i 查询几乎相同的 cell 范围（Pass1 pad=100mm，
Pass2 pad=0），2659 次查询。合并为一次 pad=100mm 查询并缓存候选供 Pass2
复用：Pass2 的 pad=0 范围是 pad=100mm 的子集，`_seg_intersection` 精确过滤
不相交的候选，功能等价。

- query_bbox 调用 2659 → 1310（减半）
- 基准中位数 1.576s → 1.388s

### 8.2 _bbox_iou 微优化（`95a0fac`）

原实现重复调用 `a.get`/`b.get`（8 次/调用），43753 次调用共 35 万次
`dict.get`。改用局部变量缓存 width/height/x/y，减少重复 dict 访问。

### 8.3 基准性能

50MB 基准图（`baa-file-2319613b52cb.dxf`，48844 图元）analyze 中位数：
- 优化前（DDA 版本）：1.576s
- 优化后（查询合并 + _bbox_iou）：1.388s

> 注：基准图被 `.gitignore` 排除，CI 上 `data_guard` 检测到图缺失会跳过
> 性能门禁（输出 Notice），不因超阈值失败。本地开发仍应保持达标。

### 8.4 查询优化尝试（负优化，已回退）

以下三种 `query_bbox` 替代方案均**负优化**，已回退（保留全 cell 遍历 + set 去重）：
- **gen 戳数组去重**：`_seen` 列表扩展 + `_gen` 自增开销超过 set 去重
- **有序 cell 键二分**：排序 14 万键 + bisect 元组比较慢于直接遍历
- **行索引二分**：`_build_row_index` 重建排序 + 双层索引慢于直接遍历

结论：`_SpatialGrid` 的 cell 数（14 万）相对查询次数（1310）不大，全遍历
开销可接受；替代方案的重建/二分开销超过节省的空 cell 遍历。

---

## 9. 后续优化：_find_faces 面过滤层判定缓存 + pos_index（2026-11-10）

> 独立提交 `f63a684`。

### 9.1 背景

`_find_faces` 的 profile 显示两个热点：
1. **面过滤层判定**：对每条边做 `any(kw in layer for kw in _NON_ROOM_LAYER_KW)`
   （36 关键字子串匹配），191 万次生成器调用，占 `_find_faces` 66%。
2. **`neighbors.index(prev)`**：O(k) 线性查找。

### 9.2 优化

1. **层判定 lru_cache**：新增 `_is_non_room_layer(layer)` 用 `@lru_cache(4096)`
   缓存判定结果。实测 dongguan 53290 次边访问只有 2 个唯一层名（'' 和 '0'），
   缓存命中率 100%。O(36) 子串匹配降为 O(1) 字典查找。
2. **pos_index**：`_sort_edges_at_nodes` 额外构建 `pos_index[nid][neighbor]=position`
   字典，`_find_faces` 用 O(1) 查找替代 `neighbors.index(prev)`。

### 9.3 功能等价性

五图房间数完全一致：villa 22 / stadion 46 / dongguan 186 / plans 30 /
mosque 0（均不变）。`_find_faces` 返回 faces 数 10696 不变。

### 9.4 性能提升（dongguan）

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| `_find_faces` 函数调用 | 2382111 | 357091（-85%） |
| `_find_faces` profile 耗时 | 0.390s | 0.103s |
| `_find_faces` 裸计时 | 0.096s | 0.031s（3.1x） |

> 注：基准图（50MB 电气图）analyze 中位数受系统负载波动大（1.27–1.93s），
> 本次优化主要收益在含大量房间的图纸（dongguan 等），基准图房间数 188
> 收益有限。CI 上基准图被 `.gitignore` 排除，性能门禁会跳过。

---

## 10. 后续优化：_SpatialGrid 改嵌套 dict（2026-11-10）

> 独立提交 `0ac0eee`。

### 10.1 背景

`_SpatialGrid.cells` 原为 `Dict[(kx,ky), List[int]]`（defaultdict）。`query_bbox`
遍历 bbox 内所有 cell，对空 cell 仍要构造 `(kx,ky)` 元组并哈希。实测 dongguan
`query_bbox` 遍历 135 万 cell 中 **73% 为空**（空 cell 占比 0.7329）。

### 10.2 优化

改嵌套 dict `cells[kx][ky] = [idx]`：`query_bbox`/`query_point` 先查
`row = self.cells.get(kx)`，row 为 None 则整列跳过，避免空 cell 的元组
构造/哈希。新增 `_append_cell` 辅助方法统一插入（insert_point/insert_segment
共用）。

### 10.3 功能等价性

五图房间数完全一致：villa 22 / stadion 46 / dongguan 186 / plans 30 /
mosque 0（均不变）。基准脚本验证 2791 条线段 query_bbox 结果逐条一致。

### 10.4 性能提升（dongguan，完整 analyze profile）

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| `query_bbox` | 1.66s | 0.855s（-48%） |
| `_split_t_junctions` | 2.34s | 1.36s（-42%） |
| 完整 analyze | 10.2s | 7.8s（-24%） |

> 注：之前 §8.4 尝试的 3 种 `query_bbox` 替代方案（gen 戳数组、有序 cell 键
> 二分、行索引二分）负优化，是针对**去重机制**；本次嵌套 dict 是**数据结构**
> 优化（空 cell 跳过），两者不同，不冲突。
