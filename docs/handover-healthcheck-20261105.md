# BAA 交接体检报告

> 执行日期：2026-11-05　｜　性质：只读体检（未改动任何项目代码）
> 数据来源：`git` 实况、全量 `pytest`、`scripts/benchmark_semantic_analyze.py`、cProfile 分阶段剖析（50MB 电气图 `baa-file-2319613b52cb.dxf`，48.9MB / 48844 图元 / 1680 标注 / 10119 实体）

---

## 一、结论（先看这里）

**项目状态：功能健康，交付不干净。**

| 维度 | 结论 |
|---|---|
| 正确性 | 良好。全量 **2895 passed / 0 failed**，两轮跑结果一致 |
| 性能 | **不达标**。基准中位数 **1.088s**，CI 门禁阈值 1.0s，当前**会挂** |
| 代码完整性 | 有问题。上一轮三项核心优化**均未提交**（P0-2 网格模块整个文件还是未跟踪状态） |
| 下一步 | **先把未提交的优化落库并复测**，再治理真正的性能热点 `_merge_overlapping`（占总耗时 23.6%） |

一句话：**别再开发新功能了，先把工作区里悬着的三项优化提交、把 1.088s 压回 1.0s 以内。**

---

## 二、代码现状

### 2.1 分支与提交

- 当前分支：`main`
- 工作区：**16 个已修改文件**（无暂存区内容），另有大量未跟踪文件
- 最近提交（HEAD → 新）：

| 提交 | 说明 |
|---|---|
| `de87f02` | refactor(review): 删除 `_build_findings` 死代码（P0-4） |
| `8d38d61` | feat(test): P0-3 数据目录隔离 + 基线刷新 |
| `d757914` | feat(review): P0-2 假满分治理——规则可达性 coverage 字段与证据不足语义 |
| `ffcef1e` | fix: 冒烟测试暴露的 5 处功能缺陷与审查性能优化 |

### 2.2 三项优化的提交状态（逐项核实）

| 优化项 | 状态 | 证据 |
|---|---|---|
| **P0-2 网格索引优化** | ❌ **未提交** | `src/baa_engine/semantic_analyzer/spatial_grid.py` 为未跟踪文件（`??`）；`relations.py` 新增 `from .spatial_grid import ...`；`merge.py` 的 per-type 网格改造未提交 |
| **P0-1 规则可达性优化** | ⚠️ **部分提交** | `HEAD:review_routes.py` 已含 9 处 `coverage`（来自 `d757914`）；但工作区 diff 仍新增 6 处 `coverage`，`fp_rate_audit.py` 也未提交 |
| **扫线法层名缓存** | ❌ **未提交** | `room.py` 在工作区新增 `_wall_layer_cache`；`HEAD:room.py` 中该标识出现 0 次 |

### 2.3 未跟踪但属于项目资产的文件

- `src/baa_engine/semantic_analyzer/spatial_grid.py`（网格基础设施，**核心**）
- `src/tests/test_spatial_grid.py`（对应测试）
- `scripts/benchmark_semantic_analyze.py`（CI 性能门禁脚本，**必须在库里**，否则 CI `semantic_perf` job 找不到脚本）
- `scripts/generate_evac_samples.py` / `generate_specialized_rooms.py` / `verify_specialized_rooms.py`
- `docs/evac-samples-expansion-20261105.md`

### 2.4 仓库卫生风险（建议本次一并清理）

未跟踪目录/文件混杂：`UnRAR.exe`、`license.txt`、`.trae-html-share-packages/*.zip`、`grid-optimization-summary/`、`p131-fix-report-20261103/`、`docs/baa-product-assessment-*/`（含 4 个字体与 echarts.min.js）。这些是报告产物，应进 `.gitignore` 或移出仓库根目录。

---

## 三、测试现状

```
2895 passed, 28 skipped, 14 deselected, 10 warnings in 138.92s
```

- **0 failed**。两次独立运行结果一致（138.92s / 144.49s）。
- `28 skipped`：`pg` 标记（需 `BAA_TEST_PG_URL`）等条件型跳过。
- `14 deselected`：来自 `pyproject.toml` 的 `addopts = "-m 'not slow and not real_drawing'"`，即 `slow` 与真实图纸基线用例默认不跑。
- 警告均为第三方库弃用/ORM 笛卡尔积提示，非本项目缺陷。

> 注意：默认跑**不含**真实图纸基线（`real_drawing`）。交接后若要验证解析层回归，需单独 `-m real_drawing` 且需配置图纸数据源。

---

## 四、性能现状

### 4.1 端到端基准（CI 同款脚本）

```
run1 1.078s / run2 1.088s / run3 1.098s   中位数 1.088s
阈值 1.0s  →  ❌ 失败（性能回退）
```

CI 配置（[test.yml](file:///d:/OpenClawData/BAA/.github/workflows/test.yml#L103-L131)）：
`python scripts/benchmark_semantic_analyze.py --threshold 1.0 --runs 3`

脚本 docstring 记录的优化后实测为 0.425s，当前实测 1.088s，**相对记录值回退约 2.5×**。本机 CPU 差异可能存在，但 1.088s 已实打实超过门禁，必须当作 blocker。

### 4.2 分阶段耗时（端到端 1.046s）

| 阶段 | 耗时 | 占比 |
|---|---:|---:|
| `_classify_entities` 合计 | 0.335s | 32.1% |
| └ **`_merge_overlapping`** | **0.247s** | **23.6%** |
| └ 图层/几何分类（不含 merge） | 0.088s | 8.4% |
| `_bind_dimensions` | 0.164s | 15.7% |
| `_build_relations` | 0.109s | 10.5% |
| └ Phase1 相邻关系（`min_edge_distance` 67572 次） | 0.070s | 6.7% |
| `_infer_corridor_widths` | 0.073s | 7.0% |
| `_sweep_line_detect_rooms` | 0.069s | 6.6% |
| `_detect_floor_levels` | 0.054s | 5.2% |
| `_assign_entities_to_floors` | 0.023s | 2.2% |
| `_infer_room_types` | 0.021s | 2.1% |
| `_inject_geometry_attributes` | 0.005s | 0.5% |
| 其余（缓存指纹、图例学习、疏散连通性校验等） | ≈0.193s | ≈18% |

### 4.3 你问的两个函数：结论与假设不同

| 函数 | 实测占比 | 判断 |
|---|---:|---|
| `_build_relations` | **10.5%** | 次要瓶颈，非主因 |
| `_infer_room_types` | **2.1%** | **不是热点**。已于 P0-2 做 TEXT 网格化（`_TEXT_CELL=2000mm`），196 个 room × 少量 cell，主循环仅做 `type=="room"` 过滤，10119 实体下开销可忽略 |

**真正的第一热点是 `_merge_overlapping`（23.6%）**，其次 `_bind_dimensions`（15.7%）。

### 4.4 各自的具体热点

**`_merge_overlapping`（0.247s，单次调用）** — [merge.py](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/merge.py#L98-L134)
- 已按类型分网格（`CELL_SIZE=1000mm`），但**长实体跨格爆炸**：`range(gx1-1, gx2+2)` 对 80m 长墙在单轴就展开 83 个 cell，最多 **83×83 ≈ 6889 次 `grid.get`**；而图元里长墙/长走廊占比高。
- 每个实体都 `candidates = set()` 新建 + `sorted(candidates)` 排序，10119 实体 → 大量短生命周期对象与排序开销。
- 缺少廉价 AABB 快速拒绝（面积预过滤虽在，但 `_compute_iou` 前仍有大量候选进入）。

**`_bind_dimensions`（0.164s）** — [relations.py](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/relations.py#L429-L478)
- `_EXPAND = 10` + `_BIND_CELL = 1000mm` → 每个标注固定遍历 **21×21 = 441 个 cell**，1680 标注 = **74.1 万次循环**；`nonempty_cells` 只省了 `dict.get`，循环本身没省。
- `_dim_projection_ratio` 13130 次调用（0.020s），单次便宜但调用量大。

**`_build_relations`（0.109s）** — [relations.py](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/relations.py#L73-L125)
- Phase1 相邻关系：67572 次 `min_edge_distance`（0.070s，占该函数 64%）。候选对进入精确边距计算前**没有 AABB 间隙快速拒绝**。
- 长实体同样跨多 cell，且 `compared` 元组集合去重有额外哈希开销。

---

## 五、接续开发清单（按优先级）

### T1（P0，无依赖）落库三项悬空优化 + 复测性能门禁

- 内容：提交 `spatial_grid.py`、`test_spatial_grid.py`、`merge.py`/`relations.py` 网格改造、`room.py` 层名缓存、`benchmark_semantic_analyze.py`；同时补齐 `review_routes.py`/`fp_rate_audit.py` 剩余可达性改动。
- 验收：
  1. `git status` 中 `src/` 无未提交/未跟踪的优化相关文件；
  2. `pytest src/tests` **≥2895 passed，0 failed**；
  3. `python scripts/benchmark_semantic_analyze.py --threshold 1.0 --runs 3` 通过（中位数 ≤1.0s）；
  4. `python -m pytest src/tests/test_spatial_grid.py` 全通过。
- 说明：**必须先做**，否则后续性能优化无法与基线区分。

### T2（P0，依赖 T1）`_merge_overlapping` 长实体跨格治理

- 内容：对超大 bbox 的跨格插入设上限（或按 `MAX_CELLS_PER_ENTITY` 截断并使用粗粒度兜底索引）；移除逐实体 `sorted(candidates)`；在 `_compute_iou` 前加 AABB 快速拒绝。
- 验收：
  1. `_merge_overlapping` 耗时 **≤0.10s**（当前 0.247s，降幅 ≥60%）；
  2. 合并输出**完全等价**：同一 50MB 图下输出实体总数与 `(entity_id, type, bbox)` 排序后逐项一致（10119 输入，输出需与基线 diff 为零）；
  3. 端到端中位数 **≤0.90s**；
  4. 全量测试 ≥2895 passed。

### T3（P1，依赖 T1）`_build_relations` Phase1 加 AABB 间隙预筛

- 内容：在调用 `min_edge_distance` 之前，用 bbox 间轴向间隙快速判定 `gap ≥ ADJACENT_THRESHOLD(50mm)` 即跳过；对长实体避免重复入格。
- 验收：
  1. `_build_relations` **≤0.060s**（当前 0.109s）；
  2. `adjacent` 关系条数与基线**完全一致**；
  3. 全量测试 ≥2895 passed。

### T4（P1，依赖 T3 的空间索引封装）`_bind_dimensions` 网格粒度调优

- 内容：`_BIND_CELL` 1000→5000mm、`_EXPAND` 10→2（覆盖半径仍为 10m），把每标注 441 次 cell 循环降到 25 次；复用 `spatial_grid` 的候选接口。
- 验收：
  1. `_bind_dimensions` **≤0.080s**（当前 0.164s，降幅 ≥50%）；
  2. 尺寸绑定命中数**与基线一致**（`relations.py` 注释记录的基线为 1389）；
  3. 全量测试 ≥2895 passed。

### T5（P2，无硬依赖）修复 `fire_elev` 样本被误判为电气图

- 背景（本轮实测发现）：`synth_fire_elev_lobby.dxf` / `synth_fire_elevator.dxf` 在 `fp_rate_audit` 中 `scope_mode=skipped`，不进原子函数判定。根因是 `drawing_classifier` 的文件名规则里电气含 `"EL"` 子串，命中了 `fire_elev`（`elevator` 缩写）。属误判，非解析层缺陷。
- 内容：将 `EL` 匹配改为词边界/前缀约束（如 `EL-`、`EL_`、`ELEC`），避免命中 `elev`。
- 验收：
  1. 两个样本在 `fp_rate_audit` 中 `scope_mode != skipped` 且 `evaluated_rules > 0`；
  2. 回归断言：含 `EL-`/`ELEV`/`ELEC` 前缀的真实电气图仍判为「电气」（新增单位测试）；
  3. 全量测试 ≥2895 passed。

---

## 六、给接手人的 3 条提醒

1. **不要相信 docstring 里的性能数字**。`_build_relations` 注释写「占 total <0.5%」「瓶颈在 `_bind_dimensions` 34.5s」，与当前实测（10.5% / 0.164s）量级完全不符——那是旧图/旧版本的遗留描述。
2. **未提交改动分散在 16 个文件里**，跨了语义解析、审查规则、反构引擎三个模块。T1 提交时应按模块拆分 commit，不要一把梭，否则后续 blame 失效。
3. **真实图纸基线默认不跑**（`real_drawing` 被 deselect）。任何解析层改动都要额外跑真实图纸基线，单靠 2895 条单测不足以证明无语义回归。

---

## 七、更新说明（2026-11-06，T1–T5 执行后）

本节用于覆盖上文已被后续实测推翻的结论，冲突时以本节为准。

### 已完成项与提交

- T1：`94ab487`（网格基础设施/可达性等悬空改动落库）
- T2：`e9b09db`（`_merge_overlapping` 跨格治理）
- T3：`b3ef5c7`（`_build_relations` AABB 前置拒绝 + 候选网格）
- T4：`5ef2d88`（`_bind_dimensions` 网格查询改列索引二分）
- T5：`aa742b6`（短 ASCII 关键词改词元边界匹配，修复 `fire_elev` 误判）
- 可复现性：`9b646a3`（Phase 5 房间-门连接按 room_id 排序）

### 被推翻 / 需修正的旧数据

1. **`_build_relations` 注释的「占 total <0.5%」「瓶颈在 `_bind_dimensions` 34.5s」**：已删除。当前实测（48.9MB 电气图 / 10119 实体 / 1680 标注，宿主机负载 ≈50%）为 `_build_relations` ≈0.05–0.07s，约占 analyze 总量（≈0.70–0.74s）的 8%。
2. **T2 基线「当前 0.247s」**：该值已过期。T2 优化后 merge 为 0.056s（空闲窗口），负载 ≈50% 时 ≈0.11s；端到端从 T2 前的 0.508s 降到 0.447s（当时窗口）。
3. **T3 基线「当前 0.109s」**：T3 优化后实测 0.070s（当时窗口），之后在当前窗口复测 0.056–0.058s。
4. **T4 方案描述「`_BIND_CELL` 1000→5000mm、`_EXPAND` 10→2」**：实际落地改为「按 gx 列 + 列内 gy 二分」定位候选，未放大 cell（`_BIND_CELL` 仍 1000mm、`_EXPAND` 仍 10），避免把邻域粒度改粗带来等价性风险。实测 0.164s → 0.081s（负载 ≈50%）。
5. **T5 回归项写「含 `EL-`/`ELEV`/`ELEC` 前缀的真实电气图仍判电气」**：其中 `ELEV`/`elev` 属电梯语义，修复后应**不再**判电气。真实电气仍命中的是 `EL` 词元、`EL1`/`EL-1`、`EL_` 前缀、`ELEC` 与中文电气关键词。两个消防电梯样本已实测 `scope_mode=grid`（非 skipped），`evaluated_rules` 分别为 11 / 14。
6. **「未提交改动分散在 16 个文件」**：已按 T1–T5 分模块提交，`src/` 下无未提交优化改动。

### 可比基准复测（2026-11-06）

同一脚本 `scripts/benchmark_semantic_analyze.py --threshold 1.0 --runs 5`、同一张 48.9MB 图；T2 版本用 `e9b09db` 的独立 worktree 复跑（脚本自 T2 起未改动），交替采样两轮：

| 轮次 | T2 版（e9b09db）中位数 | 当前 HEAD 中位数 | 采样时 CPU 负载 |
|---|---|---|---|
| 第 1 轮 | 0.879s（最大 1.499s） | 0.761s（最大 1.235s） | 40–48% |
| 第 2 轮 | 0.859s（最大 1.350s） | 0.720s（最大 1.332s） | 34–42% |

- **条件说明**：宿主机负载 34–48%，**不满足「相对空闲」标准**（本轮未等到 <20% 的窗口）；上述数字只在同负载条件下互相可比，不能与历史上安静窗口的 0.447s 直接比较。
- 结论：同等条件下 HEAD 较 T2 版下降约 13%–16%。
- 全量测试：**2902 passed / 0 failed / 28 skipped / 14 deselected**（新增 7 条 T5 回归）。
- 可复现性：`PYTHONHASHSEED=1` 与 `=2` 下，10119 实体 / 1017 关系 / 612 bindings 的规范化 JSON sha256 完全一致。

