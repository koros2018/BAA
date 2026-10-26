# T-C8 IFC/STEP 输出 — 验收证据链

日期：2026-10-26　分支：main

## 1. 目标与范围

Roadmap 阶段 C 的 T-C8「IFC/STEP 输出」（关联 C8，延后支线）：
IfcOpenShell 输出 IFC4 + CadQuery 输出 STEP（独立文件）。

验收标准（roadmap）：

- [x] 5 张平面图 Hausdorff 距离 ≤ 2mm。

## 2. 实现设计

### 2.1 引擎与许可

| 组件 | 版本 | 许可 | 说明 |
|---|---|---|---|
| IfcOpenShell | 0.9.0.post1 | LGPL-3.0 | IFC4 写出/读回，动态导入主进程直调 |
| CadQuery (OCP) | 2.8.0 | Apache-2.0 | STEP AP214 写出/读回 |

### 2.2 数据流

```
DXF → DrawingParser.parse → t3_components（mm 轴对齐墙 seg / 门窗柱实例）
    ├─ ifc_export.export_ifc4  → .ifc（IFC4，SI 米制；墙=IfcWall+矩形拉伸体，
    │                             profile 居中定位=墙矩形中心，柱/门/窗同法盒体）
    └─ step_export.export_step → .step（AP214，mm 原生单位；逐构件盒体 compound）
```

- 墙足迹矩形口径两模块共用（`ifc_export.wall_rect_mm` 等四个纯函数换算）。
- 依赖缺失/无墙构件时导出返回 None 并降级，不抛异常、不落空文件。
- 读回校验：IFC 取 IfcWall 的 IfcRectangleProfileDef 参数重建足迹；STEP 按
  solid BoundingBox 重建（墙先于柱/门窗写入，顺序对齐）。

### 2.3 Hausdorff 口径（geometry_metrics.hausdorff_2d）

两组足迹矩形边界均匀采样（角点 + 每 50mm），对称 Hausdorff =
max(源点到目标集最近距离, 目标点到源集最近距离)，单位 mm。

## 3. 验收实测（5 张合成 T3 平面图）

| 图纸 | 墙数 | 柱 | 门 | 窗 | IFC Hausdorff | STEP Hausdorff |
|---|---|---|---|---|---|---|
| plan1_single_room 6000×4200 | 4 | 1 | 1 | 0 | 0.0mm | 0.0mm |
| plan2_two_rooms 8000×5000（100 隔墙） | 5 | 0 | 1 | 1 | 0.0mm | 0.0mm |
| plan3_hall_columns 12000×8000（300 墙） | 4 | 2 | 1 | 0 | 0.0mm | 0.0mm |
| plan4_windows 9000×6000 | 4 | 0 | 1 | 2 | 0.0mm | 0.0mm |
| plan5_grid 10000×10000（2×2 网格） | 6 | 1 | 1 | 0 | 0.0mm | 0.0mm |

5 张图 IFC/STEP 双向 Hausdorff 均 **0.0mm** ≤ 2mm 验收线。
链路：合成 DXF 落盘 → DrawingParser 完整解析 → 导出 → 重新读回文件比对，
覆盖「解析→导出→文件往返」全路径，非内存自洽。

## 4. 测试与回归

- 新增 `src/tests/test_ifc_step_export.py` 16 项：矩形换算 / Hausdorff 口径 /
  5 图参数化验收 / 构件计数一致性 / 无墙降级；依赖缺失时 skip（CI 无引擎不阻塞）。
- 全量回归：见 `regression.txt`。

## 5. 变更清单

| 文件 | 变更 |
|---|---|
| `src/baa_engine/ifc_export.py` | 新增：IFC4 导出 + 墙足迹读回 |
| `src/baa_engine/step_export.py` | 新增：STEP 导出 + 墙足迹读回 |
| `src/baa_engine/geometry_metrics.py` | 新增：2D Hausdorff 距离 |
| `src/tests/test_ifc_step_export.py` | 新增：16 项单测与 5 图验收 |
| `requirements.txt` | 新增：ifcopenshell / cadquery（CI test.yml 直装本文件，天然同步） |

## 6. 边界与后续

- 输出几何为墙/柱/门窗的规则盒体（轴对齐矩形足迹拉伸），不含弧形墙/斜墙——
  T3 识别器当前仅产轴对齐墙 seg，导出忠实于识别结果。
- 门块无尺寸字段，门洞宽取标称 900mm；该标称值不影响墙足迹 Hausdorff 口径。
- 后续若需对接 BIM 软件深化，可在 IfcWall 上补 IfcOpeningElement 真实开洞。
