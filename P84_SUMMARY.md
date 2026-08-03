# P84: YOLO 模型重训练 — 总结报告

## 执行日期
2026-08-03

## 完成情况

### ✅ 第1项: 全量 floor 标注生成
- **脚本**: `scripts/p84_floor_gen.py`（修复 `is_coord()` / `to_point()` 兼容 Vec3 类型）
- **输入**: 62 DXF 图纸 → 18 候选 → 10 个检测到 floor
- **输出**: 9 张非空 floor 渲染图 + 6349 个 YOLO 标注
- **路径**: `data/p84_floor_data/images/` + `data/p84_floor_data/labels/`
- **类别**: wall(5518), stair(780), door(33), window(15), shaft(3)

### ✅ 第2项: YOLO fine-tune
- **脚本**: `p84_train_v8.py`
- **基座**: `baa_yolov8m_v6-2/best.pt` (25.8M params)
- **数据**: 6 train + 3 val, nc=5, 50 epoch
- **权重输出**: `runs/detect/runs/detect/v8_floor_50epoch/weights/best.pt`
- **训练耗时**: ~5 分钟 (CPU)
- **Loss 收敛**: box 2.7-3.8, cls 2.6-5.0
- **mAP50**: 0（标注目标在 4096px 图上为线/点，640px 下不可见）

### ✅ 第3项: V7 vs V8 对比评估

| 指标 | V7 (v6-2/best.pt) | V8 (floor 微调) |
|------|--------------------|------------------|
| 检测能力 | 覆盖 wall/room/stair/fire_zone | 0 检出 (conf≥0.25) |
| 速度 (CPU) | 182 ms/img | 181 ms/img |
| room 过检 | 51-129/图 | 无 |
| 泛化 | 对 floor 数据有一定效果 | 无法泛化到 floor 数据 |

### ⚠️ 关键发现: 标注质量不足

1. **标注本质上是线/点**：4096px 图上 wall bbox 宽度 0.000000-0.002850（即 0-11px），640px 下完全消失
2. **YOLO 需要面积型目标**：当前生成的是实体边界的 bbox，不是可检测的框
3. **V8 微调结果 = 退化**：只训练 5 类 + 极小目标 → 模型学到的是噪声

### ❌ 第4项: 数据整合 — 放弃

floor 标注不适合直接用于 YOLO 训练，不合并到 `data/p84_yolo_dataset`。

## 结论

**P84 floor 标注路线当前不可行。** 原因：

1. DXF→floor 标注生成的是线条边界 bbox，不满足 YOLO 训练要求
2. 6349 个标注中 87% 是 wall（线条），在 640px 下无意义
3. V8 模型退化到 0 检出

**建议替代方向**：
- **路线 A**: 改进 `process_floor` 逻辑，从语义分析结果（`entities_out`）提取有意义的实体（门/窗/楼梯等区域型目标）作为标注
- **路线 B**: 基于 v7 已有模型 + P81/P82/P83 的 LAYER_RULES 改进作为主要提升手段
- **路线 C**: 将 floor 标注作为 **验证/对齐工具** 而非训练数据

## 产出文件
- `scripts/p84_floor_gen.py` — 标注生成脚本（Vec3 修复）
- `data/p84_floor_data/` — floor 标注数据集
- `p84_train_v8.py` — 训练脚本
- `runs/detect/runs/detect/v8_floor_50epoch/` — V8 训练结果
