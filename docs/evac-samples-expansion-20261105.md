# 疏散语义样本扩充 — 变更摘要

**日期**：2026-11-05
**范围**：解析层疏散语义识别 + 合成样本扩充
**测试**：全量 2894 passed, 28 skipped（1 个 rate_limit 时间窗口偶发失败，单独重跑通过）

---

## 一、背景与目标

现有合成样本疏散语义覆盖偏弱：19 张样本中仅 4 张有完整 `stair+corridor+exit` 组合，多数只有孤立 `exit`；楼梯间（`staircase`）、前室（`antechamber`/`staircase_lobby`）、避难间/层（`refuge_room`/`refuge_floor`）、消防电梯前室（`fire_elevator_lobby`）等关键疏散语义完全缺失。

本次目标：**扩充带完整疏散语义的合成样本**，并修复阻碍特化疏散语义识别的解析层缺陷。

---

## 二、解析层修复（3 处）

### 1. `_classify_by_text` 关键词顺序修复
**文件**：[classify.py](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/classify.py#L555-L614)

特化关键词被泛化关键词抢先命中，导致误标：

| 误标现象 | 根因 | 修复 |
|---|---|---|
| `SMOKE_PROOF_STAIR` → `smoke_detector` | 泛化 `SMOKE` 先命中 | `SMOKE_PROOF_STAIR`/`SMOKE_PROOF_LOBBY` 提到 `SMOKE` 之前 |
| `FIRE_ELEV_LOBBY` → `fire_elevator` | 泛化 `FIRE_ELEV` 先命中 | `FIRE_ELEV_LOBBY` 提到 `FIRE_ELEV` 之前 |
| `REFUGE_FLOOR`/`REFUGE_ROOM`/`REFUGE_AREA` → `floor` | 泛化 `FLOOR`/`层` 先命中 | 避难特化关键词提到 `FLOOR` 之前 |

### 2. `_classify_by_layer` 特化图层优先
**文件**：[classify.py](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/classify.py#L277-L292)

`STAIRCASE` 图层命中 `"STAIR"`（子串匹配）→ `stair` 而非 `staircase`。子串匹配按 dict 插入顺序，`STAIR` 先于 `STAIRCASE` 插入导致误标。

新增 `_SPECIALIZED_FIRST` 特化图层优先匹配表（`STAIRCASE_LOBBY`/`STAIRCASE`/`SMOKE_PROOF_STAIR`/`SMOKE_PROOF_LOBBY`/`FIRE_ELEV_LOBBY`/`REFUGE_*`），在通用子串匹配之前返回特化类型。

### 3. 踏步线误识别修复
`STAIRCASE`/`SMOKE_PROOF_STAIR` 图层的踏步线（LINE 平行阵列）此前散落为 21 个孤立 `stair`。图层特化优先修复后，踏步线与轮廓统一归为 `staircase`/`smoke_proof_stair`。

---

## 三、新增合成样本（12 张）

**生成脚本**：[generate_evac_samples.py](file:///d:/OpenClawData/BAA/scripts/generate_evac_samples.py)

| 样本 | 识别出的疏散语义 |
|---|---|
| `synth_staircase_corridor.dxf` | **staircase + corridor + exit**（完整疏散链）|
| `synth_staircase_lobby.dxf` | staircase + staircase_lobby（楼梯间前室）|
| `synth_smoke_proof_stair.dxf` | smoke_proof_stair + smoke_proof_lobby（防烟楼梯）|
| `synth_anteroom.dxf` | staircase + antechamber（前室）|
| `synth_refuge_room.dxf` | refuge_room（避难间）|
| `synth_refuge_floor.dxf` | refuge_floor（避难层）|
| `synth_fire_elev_lobby.dxf` | fire_elevator_lobby（消防电梯前室）|
| `synth_scissor_stair.dxf` | scissor_stair（剪刀楼梯）|
| `synth_external_stair.dxf` | external_stair（室外楼梯）|
| `synth_escape_stair.dxf` | escape_stair + corridor（疏散楼梯）|
| `synth_refuge_passage.dxf` | refuge_passage + corridor（避难走道）|
| `synth_fire_elevator.dxf` | fire_elevator + fire_elevator_lobby（消防电梯）|

样本目录：`data/drawings/real/synth/`（共 24 张合成样本）

---

## 四、验证结果

### 疏散语义覆盖对比

| 指标 | 扩充前 | 扩充后 |
|---|---|---|
| 有完整 `stair+corridor+exit` 组合 | 4 张 | 5 张 |
| 识别出楼梯间（`staircase`）| 0 张 | 4 张 |
| 识别出前室（`antechamber`/`staircase_lobby`）| 0 张 | 2 张 |
| 识别出避难间/层 | 0 张 | 2 张 |
| 识别出消防电梯前室 | 0 张 | 1 张 |
| 识别出剪刀楼梯（`scissor_stair`）| 0 张 | 1 张 |
| 识别出室外楼梯（`external_stair`）| 0 张 | 1 张 |
| 识别出疏散楼梯（`escape_stair`）| 0 张 | 1 张 |
| 识别出避难走道（`refuge_passage`）| 0 张 | 1 张 |
| 识别出消防电梯（`fire_elevator`）| 0 张 | 1 张 |

### 回归测试
- 全量测试套件：**2894 passed, 28 skipped, 14 deselected**（1 个 rate_limit 时间窗口偶发失败，单独重跑通过）
- 分类相关定向测试（atomic_functions / room_type_infer / table_exclusion）：1755 passed

---

## 五、涉及文件清单

| 文件 | 改动类型 |
|---|---|
| `src/baa_engine/semantic_analyzer/classify.py` | 修改（关键词顺序 + 特化图层优先 + 特化楼梯/避难走道）|
| `scripts/generate_evac_samples.py` | 新增（疏散样本生成器）|
| `data/drawings/real/synth/synth_*.dxf` | 新增 12 张样本 |

> 注：`room.py`/`atomic_functions.py`/`reverse_engine.py`/`room_type_infer.py` 的改动来自前序「RoomType 扩展与特化房间合成样本」任务，非本次疏散语义扩充增量。
