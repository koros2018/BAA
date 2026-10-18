# T-A4 属性抽取补齐 · 验收证据链

> 任务：`docs/baa-roadmap-v4-tasks.md` T-A4（关联缺口 G9 / Roadmap A4）
> 基线：`v2.5.79-stable`（改前 = main HEAD 未提交改动前；改后 = 同一工作区含 T-A4 改动）
> 数据：真实图纸库 252 张 DXF（`D:\BaiduNetdiskDownload\测试图纸` 全量）
> 日期：2026-10-17

---

## 1. 改动清单

| 文件 | 改动 |
| --- | --- |
| `src/baa_engine/semantic_analyzer/geometry_attributes.py` | **新增** Step 3.7：T3 native 实例字段提升（墙 `_t3_wall_seg`→width/length、窗 `_t3_window_bbox`→width、柱 bbox→width/height）+ 线元 bbox 退化实体注入真实跨度 `length`（geometry_length，非臆测；厚度/净宽不做几何臆测） |
| `src/baa_engine/semantic_analyzer/main.py` | Step 3.7 前移接入分析管线（尺寸链路 3.5 / TEXT 链路 3.6 之后） |
| `src/baa_engine/atomic_functions.py` | 修复 DIM-113 死函数（属性读取口径修正，原子函数可复算） |
| `src/baa_engine/block_semantics.py` | `$LINEPAT$`/五金件块从兜底 wall 改归 other（消除误归类） |
| `src/tools/dimension_coverage.py` | 验收工具：`--json` 证据链输出（逐文件+聚合+属性来源直方图）、`--skip/--limit` 分块、单图异常容错、逐图 gc |
| `tests/test_geometry_attributes.py` / `tests/test_ta4_atomic_recompute.py` / `tests/test_block_semantics.py` | 新增/修正测试 |

注入权威序：**T3 native > 尺寸/TEXT 标注 > bbox 几何兜底（仅 length）**，所有注入写 `_attribute_source` 追溯字段，不覆盖既有非零值。

## 2. 测试与回归

| 项 | 结果 |
| --- | --- |
| 新增单测 | 13/13 通过 |
| 全量回归 | **2398 passed / 14 skipped / 0 failed** |
| T3 验收 | ACCEPT（native 墙/门/窗/合并 F1 全 1.0，见 `docs/t3_acceptance/`） |

## 3. 覆盖率改前/改后对比（252 张真实图纸，逐图独立进程，同口径）

两侧均为 `files=252 / parsed=248 / analyze_failed=1`（4 张解析失败、1 张 `M-00-10-06.通风系统流程图…dxf` 分析异常，**两侧一致**，不影响对比公平性）。

| 指标 | 改前 | 改后 | 变化 |
| --- | --- | --- | --- |
| 实体总数 | 720148 | 715244 | -4904（block_semantics 归类修正，T3 F1=1.0 未回归） |
| 关键属性（width/clear_width/height/length 任一非 0）缺失率 | 23.50% | 22.96% | **-0.54pp** |
| 尺寸可标注类型（DIMENSIONABLE）缺失率 | 20.78% | **18.32%** | **-2.46pp** |
| 墙缺失数 | 35666 | 28850 | **-6816** |
| 楼梯缺失数 | 1743 | 1676 | -67 |
| 尺寸关联实体属性缺失（attrs_missing） | 0 / 23465 | 0 / 23465 | 两侧均无绑定后未落库 |

改后属性来源直方图（`_attribute_source`）：`geometry_length=9967`、`t3_native=7446`、`text_thickness=188`、`text_code=178`；改前无 t3_native / geometry_length 来源。

## 4. 验收标准判定

| 标准 | 判定 | 说明 |
| --- | --- | --- |
| ① 关键属性缺失率 ≤ 10% | **未达标（18.32%）** | 缺口收敛 -2.46pp 但未达线。剩余缺口归因：wall 28.9k / window 7.9k / door 2.4k / stair 1.7k，主要为无尺寸标注、无 T3 native 字段且 bbox 无法推断厚度/净宽的普通 CAD 线元墙体与门窗——按「宁缺勿错」原则不做几何臆测，需后续拓扑配对/图例推断（阶段 B 拓扑显式化）补齐 |
| ② 依赖属性的原子函数可复算且正确 | **达标** | DIM-113 死函数修复，`tests/test_ta4_atomic_recompute.py` 复算通过；attrs_missing=0（尺寸绑定实体属性 100% 落库） |

## 5. 复现命令

```powershell
# 改后（主 clone 工作区，含 T-A4 改动）
python D:/tmp/ta4_runall.py after    # 逐图独立进程，输出 D:/tmp/ta4_after_f/*.json
# 改前（HEAD 基线 worktree D:/tmp/baa_head，同口径工具）
python D:/tmp/ta4_runall.py before   # 输出 D:/tmp/ta4_before_f/*.json
# 合并
python D:/tmp/ta4_merge.py D:/tmp/ta4_after_f  D:/tmp/ta4_after_final.json
python D:/tmp/ta4_merge.py D:/tmp/ta4_before_f D:/tmp/ta4_before_final.json
```

本目录 `coverage_before.json` / `coverage_after.json` 即上述合并产物的归档副本。
