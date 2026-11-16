# 46 条未判定规则样本覆盖分析（2026-11-16）

## 1. 结论

剩余 46 条未判定规则（适用但判定 0，非 unsupported_2d / 实现门禁）**全部为样本覆盖限制**——判据载体在当前样本中不可得，**无架构缺口**（判据载体存在但 handler/注入缺失）。

可判定口径 73.3%（107/146）已接近样本覆盖上限；进一步提升需扩充样本（含 fire_zone/garage/residential_unit 容器、疏散门标注、3D 属性图纸）。

## 2. 分类汇总

| 分类 | 数量 | 说明 |
|------|------|------|
| 容器实体在样本中不存在（fire_zone/garage/residential_unit/auditorium） | 15 | COUNT-001/013/014/015/017/018/021/022/023/024/025、DIM-024 |
| 判据实体在样本中不存在（step/smoke_vent/accessible_elevator/fire_door/exit_door/fire_hose/evacuation_sign/scissor_stair/curtain_wall） | 9 | ACCESS-015、DIST-006/022/023、EXIST-035/054、DIM-084/093/097 |
| 3D 属性在 2D 图纸不可得（净高/转弯半径/扶手高度/消火栓高度） | 9 | DIM-011/031/085/086/088/098/107/108、DIM-030 |
| 实体无判据属性（width/area 未注入，bbox 为符号/标注） | 8 | DIM-106/083、AREA-001/003/007/009/015、DIM-058、COUNT-002 |
| 语义标注缺失（window 无 exterior 语义、疏散门无标注） | 4 | THERM-013、COUNT-016/020/026 |
| 建筑间距未计算 | 2 | DIST-002/021 |
| 允许性规则语义存疑 | 1 | COUNT-003 |

## 3. 逐条明细

### 3.1 容器实体在样本中不存在（15 条）

| 规则 | 适用图 | 判据载体 | 样本状态 |
|------|--------|---------|---------|
| COUNT-013 | 47 | garage/fire_zone 容器聚合出口数 | 无 garage/fire_zone |
| COUNT-024 | 47 | residential_unit/fire_zone 容器聚合出口数 | 无容器 |
| COUNT-025 | 47 | fire_zone 容器聚合出口数 | 无容器 |
| COUNT-015 | 21 | fire_zone 容器聚合出口数 | 无容器 |
| COUNT-021 | 21 | residential_unit 容器聚合出口数 | 无容器 |
| COUNT-022 | 21 | residential_unit 容器聚合出口数 | 无容器 |
| COUNT-001 | 3 | floor/fire_zone 容器聚合出口数 | floor 是楼层标签非空间范围 |
| COUNT-017 | 3 | fire_zone/residential_unit 容器聚合出口数 | 无容器 |
| COUNT-014 | 3 | fire_zone 容器聚合消防电梯数 | 无容器 |
| COUNT-018 | 1 | fire_zone 容器聚合消火栓数 | 无容器 |
| COUNT-023 | 15 | fire_zone 容器聚合消防电梯数 | 无容器 |
| DIM-024 | 47 | auditorium 容器聚合疏散门数 | 无 auditorium |

### 3.2 判据实体在样本中不存在（9 条）

| 规则 | 适用图 | 判据载体 | 样本状态 |
|------|--------|---------|---------|
| ACCESS-015 | 17 | step 实体踏步高度 | 无 step 实体 |
| DIST-006 | 11 | smoke_vent 排烟口 | 无 smoke_vent |
| DIST-022 | 1 | evacuation_sign 疏散指示标志 | 无实体 |
| DIST-023 | 1 | scissor_stair 剪刀楼梯间 | 适用图仅普通 stair；synth_scissor_stair 图幅判定 unknown 不进入平面审查 |
| EXIST-035 | 14 | accessible_elevator 无障碍电梯 | 无实体 |
| EXIST-054 | 11 | fire_door/exit_door | 无实体 |
| DIM-084 | 11 | exit_door/external_door | 无实体 |
| DIM-093 | 1 | fire_hose 消防水带 | 无实体 |
| DIM-097 | 1 | curtain_wall/fire_stop | 无实体 |

### 3.3 3D 属性在 2D 图纸不可得（9 条）

| 规则 | 适用图 | 判据载体 | 样本状态 |
|------|--------|---------|---------|
| DIM-011 | 4 | 消防车道净高 | 2D 图纸无净高 |
| DIM-031 | 4 | 消防车道转弯半径 | 2D 图纸无转弯半径 |
| DIM-085 | 4 | 消防车道净高 | 2D 图纸无净高 |
| DIM-086 | 4 | 消防车道转弯半径 | 2D 图纸无转弯半径 |
| DIM-098 | 4 | 消防车道净高 | 2D 图纸无净高 |
| DIM-108 | 4 | 消防车道净高 | 2D 图纸无净高 |
| DIM-030 | 2 | 消防救援场地宽度 | 无 width 属性 |
| DIM-088 | 1 | 消火栓栓口高度 | 2D 图纸无高度 |
| DIM-107 | 2 | 楼梯扶手高度 | 2D 图纸无高度 |

### 3.4 实体无判据属性（8 条）

| 规则 | 适用图 | 判据载体 | 样本状态 |
|------|--------|---------|---------|
| DIM-106 | 2 | external_stair 净宽 | width=None（bbox 为符号 3000×6000） |
| DIM-083 | 1 | external_stair 净宽 | width=None |
| AREA-001 | 4 | refuge_floor 面积 | area=None（bbox 为符号 375×250） |
| AREA-003 | 1 | refuge_floor 面积 | area=None |
| AREA-007 | 1 | refuge_room 面积 | area=None |
| AREA-009 | 2 | refuge_floor/room 面积 | area=None |
| AREA-015 | 2 | refuge_floor/room 面积 | area=None |
| DIM-058 | 1 | refuge_room 面积 | area=None |

### 3.5 语义标注缺失（4 条）

| 规则 | 适用图 | 判据载体 | 样本状态 |
|------|--------|---------|---------|
| THERM-013 | 15 | exterior_window 外窗语义 | window 无 exterior 标注 |
| COUNT-016 | 43 | room 容器 door_count | 无 exit_door/evacuation_door 实体 |
| COUNT-020 | 43 | room 容器 door_count | 无疏散门实体 |
| COUNT-026 | 47 | room 容器 door_count | 无疏散门实体 |

### 3.6 建筑间距未计算（2 条）

| 规则 | 适用图 | 判据载体 | 样本状态 |
|------|--------|---------|---------|
| DIST-002 | 2 | building↔building 防火间距 | 语义分析未计算建筑间距 |
| DIST-021 | 2 | building↔garage 防火间距 | 同上 |

### 3.7 允许性规则语义存疑（1 条）

| 规则 | 适用图 | 判据载体 | 样本状态 |
|------|--------|---------|---------|
| COUNT-003 | 17 | 楼梯间数量 ≥1 | 「可采用敞开楼梯间」是允许性规则，判「楼梯间 ≥1」语义存疑 |

## 4. 关键验证证据

- **fire_lane/road 实体无 width**：baa-file-5840029dbcb8.dwg 87 个 road 实体全部 width=None（bbox 为符号/标注）；synth_fire_lane fire_lane bbox 375×250 为符号。
- **external_stair 实体无 width**：synth_external_stair 22 个 external_stair 全部 width=None（bbox 3000×6000 为符号）。
- **refuge_floor/room 实体无 area**：synth_refuge_floor/room bbox 375×250 为符号，area=None。
- **DIST-023 无 scissor_stair 有效实体**：适用图 baa-file-e4a98405fd6c.dwg 仅普通 stair=132（无 scissor_stair）；synth_scissor_stair（scissor_stair=23）图幅判定 unknown（R4）不进入平面审查。
- **COUNT-016/020/026 无疏散门实体**：样本无 exit_door/evacuation_door 实体，room 容器未注入 door_count。

## 5. 提升路径建议

1. **扩充样本**（最大收益）：引入含 fire_zone/garage/residential_unit 容器的图纸，可打通 COUNT-001/013/014/015/017/018/021/022/023/024/025（15 条）。
2. **引入疏散门标注图纸**：可打通 COUNT-016/020/026（3 条）。
3. **引入 3D 属性图纸**：可打通 DIM-011/031/085/086/088/098/107/108（8 条）。
4. **建筑间距计算**（架构能力，非样本）：DIST-002/021 需语义层计算 building 间距，样本仅 2 图，收益有限。

> 注：以上为样本覆盖限制，非引擎能力缺口。引擎的注入链路与 handler 已就绪（DIST-004~010、COUNT-016/019/020/026），图纸含对应实体标注时可判定。
