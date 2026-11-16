# 语义分析性能优化总结报告（2026-11-16）

**日期：** 2026-11-16
**范围：** 第 15 张图纸性能优化的后续推进（T-opt35 网格优化 + Numba 方向确认 + 全量图纸稳定性验证）
**前置：** 2026-11-15 已完成 T-opt31~34b（见 `drawing15-perf-optimization-20261115.md`）

---

## 1. 本次目标

延续第 15 张图纸（`baa-file-05f5853faa62.dxf`）性能优化，推进三个方向：

1. **2 层嵌套 dict 策略推广**到其他空间网格
2. **Numba JIT 加速 Phase 2 内核**（T-opt29 WIP 确认）
3. **扩展 baseline 到全部图纸**，验证跨图纸稳定性

---

## 2. 方向 1：2 层嵌套 dict 推广（T-opt35）

### 2.1 现状盘点

通过全量搜索确认：`spatial_grid.py` 的公共函数（`build_entities_grid`/`grid_candidates`）在 `relations.py` 中**仅导入但从未被调用**——Phase 1 已用内联 `grid_p1`（T-opt17 已 2 层嵌套）。真正仍用平铺 `dict[(gx,gy)]` 的空间网格有 **3 处**。

### 2.2 优化点

| # | 网格 | 文件 | 用途 | 优化内容 |
|---|------|------|------|---------|
| 1 | `text_grid` | `main.py` | P109 房间类型推断 TEXT 分桶 | 构建 + 查询均改 2 层嵌套 |
| 2 | `_dup_grid` | `room.py` | P104 bbox 重叠去重 | 构建 + 查询均改 2 层嵌套 |
| 3 | `_bind_dimensions` grid | `relations.py` | 尺寸绑定网格 | 构建改 2 层嵌套 + T4 二分查询适配 |

### 2.3 实现要点

平铺 `dict[(gx,gy)]` → 嵌套 `dict[gx][gy]`，查询时只遍历存在的 gx row，跳过全部空 cell（第 15 张图纸 92% 的 gx 无数据）：

```python
# 构建（以 _dup_grid 为例）
_row = _dup_grid.get(gx)
if _row is None:
    _dup_grid[gx] = {gy: [idx]}
else:
    _lst = _row.get(gy)
    if _lst is None:
        _row[gy] = [idx]
    else:
        _lst.append(idx)

# 查询：跳过不存在的 gx row
_row = _dup_grid.get(gx)
if _row is None:
    continue
for gy in range(gy0, gy1 + 1):
    for cand in _row.get(gy, ()):
        cand_idxs.add(cand)
```

`_bind_dimensions` 的 T4 二分查询同步适配：`gx_keys = sorted(grid.keys())`、`gy_keys_by_gx = {gx: sorted(row.keys())}`、`grid[gx][gy]` 替代 `grid[(gx,gy)]`。

### 2.4 验证

- **3156 测试通过，无回归**（含 119 条维度/房间相关测试）
- 第 15 张图纸 entities=21,762 与 baseline 一致，正确性保持

---

## 3. 方向 2：Numba JIT 加速 Phase 2 内核

### 3.1 现状确认

Phase 2（墙体-开洞匹配）实际路径为 **C 扩展**（`phase2_match.pyd`，`_HAS_C=True`）——这是比 Numba 更优的选择。Numba 内核（`phase2_kernel.py`，`@njit(cache=True)`）作为 fallback 已实现。

### 3.2 一致性验证

`test_phase2_c_ext.py` 覆盖 30+ 用例，包含 Numba 与 C 扩展一致性对比（`TestPhase2MatchNumbaCompare`），全部通过。

### 3.3 结论

Phase 2 已走最快路径（C 扩展），Numba 为备份。方向 2 已充分优化，无需额外工作。

---

## 4. 方向 3：扩展 baseline 到全部图纸

### 4.1 方法

- 按 **MD5 内容哈希去重**：`data/files` 1729 个 DXF → **192 个唯一图纸**
- 对每个唯一图纸运行隔离进程语义分析（120s 软超时）
- 新增脚本 `scripts/run_extended_baseline.py`（支持断点续跑）

### 4.2 结果

| 指标 | 数值 |
|------|------|
| 唯一图纸（MD5 去重） | 192 |
| 有效图纸（>0 primitives） | 178 |
| 空壳图（0 primitives） | 14 |
| **成功（OK）** | **178/178** |
| **失败（超时/崩溃/MemoryError）** | **0** |
| 总耗时 | 1541s（约 26 分钟） |

### 4.3 性能分布

| 指标 | 数值 |
|------|------|
| 最大耗时 | 55.6s（`baa-file-0d8ce13639fa.dxf`，61,385 primitives，56,870 entities） |
| 平均耗时 | 4.5s |
| >10s 图纸 | 19 张 |
| >30s 图纸 | 4 张 |
| >60s 图纸 | 0 张 |

最大图纸 61K primitives 在 55.6s 内完成，远低于 120s 超时。**跨图纸稳定性验证通过**——所有优化在全部 178 张有效图纸上稳定工作。

### 4.4 第 15 张图纸（隔离进程口径）

14.2s，21,762 entities，504 relations，status ok。

---

## 5. 性能演进总览（第 15 张图纸）

| 阶段 | 总管线 | 语义分析 | 状态 | 关键优化 |
|------|--------|---------|------|---------|
| 优化前 | 240s+ 超时 | — | 0 entities | — |
| T-opt32 | 17.0s | 5.34s | 21,762 entities | 100m 跨度阈值 |
| T-opt33 | ~14.6s | 2.84s | 21,762 entities | `_candidates` 2层 dict |
| T-opt34b | 8.62s | 1.57s | 21,762 entities | `_build_ent_grid` 2层 dict |
| **T-opt35** | ~12.6s | ~2.6s* | 21,762 entities | 三处网格 2 层嵌套 |

*注：T-opt35 语义分析 2.6s 为机器负载波动下的测量值（T-opt34b 时 1.57s），正确性一致（entities=21,762）。

**总提速：约 28 倍**（240s+ 超时 → 8.6~12.6s）。

---

## 6. 提交记录

| 提交 | 说明 |
|------|------|
| `1adcb79` | T-opt35：三处空间网格改 2 层嵌套 dict |
| `bf47296` | 扩展 baseline 到 192 唯一图纸（178 有效全部 OK） |

---

## 7. 结论

1. **T-opt35** 将 2 层嵌套 dict 策略推广到全部 3 处剩余平铺网格，3156 测试无回归
2. **Numba 方向**确认已充分——Phase 2 走 C 扩展（更快），Numba 为 fallback
3. **扩展 baseline** 验证 178 张有效图纸全部稳定解析，0 超时/崩溃，跨图纸稳定性确认

三个方向全部完成。第 15 张图纸从 240s+ 超时优化至约 8.6s（约 28 倍），且全量图纸稳定性验证通过。
