# P84 新方向设计（2026-08-10）

## 当前状态

**YOLO 图像渲染方案已确认走不通：**
- bbox 方案：mAP50 wall=0.03, door/window/stair ≈ 0，类别严重倾斜（wall 91%）
- seg 方案：mask mAP 全部为 0，图像中线条像素太少
- 根因：DXF LINE 零厚度渲染后 <1px，YOLO 无法学习

**当前 YOLO 在实际代码中的角色：**
- `enhancement.py` 只增强 **room/corridor** 两类（其他 16 类在 YOLO_CLASSES 中但 mAP=0，等于没用）
- 合并策略：YOLO 实体只在规则解析未覆盖时补充
- 原子函数对 YOLO 实体有放宽判定（confidence×0.7, 跳过精确尺寸/面积判定）

## 方案对比

| 方案 | 思路 | 优势 | 劣势 | 工作量 |
|------|------|------|------|--------|
| **D** LSD 线段检测 | 用 Line Segment Detector 学术模型检测图纸线段，再做几何推理 | 学术验证过，专门处理细线 | 需要训练/调参、性能未知 | 大 |
| **E** DXF 直接提取 | 直接从 DXF LWPOLYLINE/REGION 提取闭合多边形 → room/corridor | 无损、精确、无需模型 | 只解决 room/corridor，需处理不规则多边形 | 小 |
| **F** 放弃 YOLO | 完全移除 YOLO 增强，只靠规则解析 | 零维护成本 | 可能损失部分召回率 | 最小 |

## 推荐路线

**P84 Phase 1: DXF 直接提取（spike，今日）**
- 验证 LWPOLYLINE closed + 面积阈值能否替代 YOLO room/corridor 检测
- 若可行 → P84 Phase 2: 正式集成到 semantic_analyzer
- 若不可行 → 评估 P84 Phase 3: LSD 方案

**P84 Phase 2: 移除无效 YOLO 类（紧跟 Phase 1）**
- YOLO_CLASSES 从 18 类裁到 2 类（room/corridor）
- 若 Phase 1 成功 → 移除全部 YOLO，DXF 提取替代
- 清理 YOLO 训练脚本、runs/ 目录

**P84 Phase 3: LSD 兜底（仅当 Phase 1 失败）**
- 研究 LSD / HED 等线段检测模型
- 训练 + 集成 + 评估

## 为什么优先做 E

1. **精确**：DXF 直接提取 = 100% 精度，零误检
2. **快**：纯算法，毫秒级
3. **小**：只需新增一个函数，不改现有架构
4. **有退路**：若不完美，仍保留 YOLO 作为回退，风险为零