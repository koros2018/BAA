# 第 15 张图纸解析性能优化总结报告

**日期：** 2026-11-15
**目标图纸：** `baa-file-05f5853faa62.dxf`（28,483 primitives → 21,762 entities）
**核心成果：** 解析耗时从 **240s+ 超时（0 entities）** 优化至 **8.62s（21,762 entities）**，约 **28 倍提速**

---

## 1. 问题背景

第 15 张图纸（`baa-file-05f5853faa62.dxf`）是测绘坐标系图纸，包含 28,483 个图元。在原始实现中：

- **解析超时（240s+）**，返回 0 entities
- 语义分析阶段发生 **O(n²) 爆炸**，内存峰值达 **26GB**（接近 OOM）
- 隔离进程分析框架下，全部 16 张图纸均因管道阻塞死锁而超时

---

## 2. 根因诊断

通过逐步 profiling（cProfile + 分阶段计时），定位到 **5 处 O(n²) 爆炸点**：

| # | 热点函数 | 所在文件 | 根因 |
|---|---------|---------|------|
| 1 | `_split_t_junctions` | `room.py` | 超长线段（>100m）DDA 覆盖数千 cell，`query_bbox` 返回海量候选 |
| 2 | `_build_ent_grid` | `text_attributes.py` | 超大 bbox 实体（wall 中位 578m）覆盖 33 万 cell/实体 → 11 亿插入 |
| 3 | `_pair_wall_thickness` | `pairing_attributes.py` | 3,311 墙（中位 578m）大量退化线元，O(n²) 配对爆炸 |
| 4 | `_build_relations` Phase 1 | `relations.py` | 超大 bbox 实体截断到中心格，中心格聚集大量实体 → compared set 爆炸（26GB） |
| 5 | `_build_relations` Phase 5 | `relations.py` | `_P5_GRID` 构建对超大 wall 遍历数百万 cell |

**关键洞察：** 第 15 张图纸所有实体跨度异常大（wall 中位 578m、facade 1150m、slab 36km），是**测绘噪声**而非建筑构件。真实建筑构件实际跨度 <100m。

---

## 3. 优化方案

### 3.1 核心策略：100m 跨度阈值（`_MAX_SPAN`）

建筑构件实际跨度 <100m（墙体/房间/门窗），超过即测绘噪声。引入 `_MAX_SPAN = 100_000.0`（mm = 100m），跳过不影响正确性（相邻阈值 50mm << 100m）。

| 模块 | 阈值常量 | 作用 |
|------|---------|------|
| `relations.py` | `_MAX_SPAN = 100_000.0` | Phase 1 相邻查询跳过 >100m 实体（发起方与被查询方均跳过） |
| `room.py` | `_MAX_SPLIT_SPAN = 100_000.0` | `_split_t_junctions` 过滤超长线段 |
| `pairing_attributes.py` | `_MAX_PAIR_SPAN_MM = 100_000.0` | `_pair_wall_thickness` 跳过 >100m 墙 |
| `text_attributes.py` | `_nx * _ny > 500` | `_build_ent_grid` 超大 bbox 退化为只入中心格 |

### 3.2 网格数据结构优化（T-opt33/34b）

空间网格从平铺 `dict[(gx,gy)]` 改为 **2 层嵌套 dict** `dict[gx][gy]`：

```python
# 优化前：平铺 dict，每个空 cell 都需 .get()
g.setdefault((gx, gy), []).append(ent)

# 优化后：2 层嵌套 dict，查询时跳过所有不存在的 gx row
row = g.get(gx)
if row is None:
    row = {}; g[gx] = row
lst = row.get(gy)
if lst is None:
    row[gy] = [ent]
else:
    lst.append(ent)
```

**原理：** 查询时只遍历存在的 gx row，跳过空 cell。第 15 张图纸中 92% 的 gx 无数据。

### 3.3 隔离进程管道阻塞修复（T-opt31）

Windows spawn 模式下，子进程 `send_bytes()` 因管道缓冲区满而阻塞，父进程 `is_alive()` 轮询不读取管道 → 死锁。修复：父进程在等待期间用 `poll(0.1)` 轮询管道，及时读取数据。

### 3.4 超时阈值调整

语义分析软超时从 300s/240s 降至 **120s**（第 15 张图纸优化后 17s 完成，最大图纸 8s，余量充足）。

---

## 4. 性能演进

### 4.1 第 15 张图纸（`baa-file-05f5853faa62.dxf`）

| 阶段 | 总管线耗时 | 语义分析 | 状态 | 关键优化 |
|------|-----------|---------|------|---------|
| 优化前 | 240s+ 超时 | — | 0 entities | — |
| T-opt32 | 17.0s | 5.34s | 21,762 entities | 100m 跨度阈值 |
| T-opt33 | ~14.6s | 2.84s | 21,762 entities | `_candidates` 2层 dict |
| **T-opt34b** | **8.62s** | **1.57s** | **21,762 entities** | `_build_ent_grid` 2层 dict |

**总提速：约 28 倍**（240s+ 超时 → 8.62s），语义分析 **-71%**（5.34s → 1.57s）

### 4.2 各热点优化效果

| 热点 | 优化前 | 优化后 | 提速 |
|------|--------|--------|------|
| `_build_relations` | 14.3s | 0.32s | **-97.7%** |
| `_split_t_junctions` | 24.4s | 0.6s | **-97.5%** |
| `_build_ent_grid` query | 312ms | 13ms | **-96%** |
| `_build_relations` Phase 5 | 70s+ | 1.0s | **-98.6%** |
| 内存峰值 | 26GB | 341MB | **-98.7%** |

---

## 5. 全量基线验证

### 5.1 16 张图纸 baseline（T-opt32 后）

**16/16 全部通过**，无超时、无 MemoryError。第 15 张图纸 17.0s 完成（21,762 entities）。

### 5.2 测试套件

**3155 passed，无回归**（含新增 8 条 DIM 提取测试）。

---

## 6. 附带产品力提升：规则覆盖率

在性能优化过程中，同步补齐了 **30 条 DIMENSION 规则的提取逻辑**（此前无提取分支，永远返回 None）：

- **实际判定可达：32.9% → 41.6%（+8.7pp）**
- 可提升未判定规则：94 条 → 73 条（-21 条）
- 新增通用 `_GENERIC_DIM_RULES` 映射表，含 4 类防误报守卫（类型门禁、疏散语义门禁、走道宽下限、合成实体过滤）

---

## 7. 提交记录

| 提交 | 说明 | 变更 |
|------|------|------|
| `1c45103` | T-opt31 隔离进程管道阻塞修复 | isolated_analysis.py |
| `1e0132f` | T-opt32 100m 跨度阈值 | 6 文件，+91/-6 |
| `c3408fe` | P0-1 通用 DIMENSION 提取补齐 | +141 行 |
| `c1ac965` | T-opt33/34 网格 2 层 dict | 2 文件 |
| `a7165d2` | T-opt34b text_attributes 2 层 dict | +16/-10 |

---

## 8. 剩余瓶颈与后续方向

当前语义分析 1.57s，剩余瓶颈均为**必要计算**（进一步优化空间有限）：

| 热点 | 耗时 | 说明 |
|------|------|------|
| `_build_ent_grid`（3次） | ~0.69s | 3 个 grid 构建必要开销 |
| `insert_segment` | ~0.60s | DDA 精确遍历（已 T-opt15 优化） |
| `_merge_overlapping` | ~0.48s | 已 P0-2/6/9 多轮优化 |
| `_classify_entities` | ~0.28s | 已 layer 缓存优化 |

**后续方向：**
1. 将 2 层嵌套 dict 策略推广到其他空间网格（如 `spatial_grid.py`）
2. 探索 Numba JIT 加速 Phase 2 内核（T-opt29 WIP）
3. 扩展 baseline 到全部 79 张图纸，验证跨图纸稳定性
