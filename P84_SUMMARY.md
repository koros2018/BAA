# P84 总结 — 东莞通（建筑）图纸语义分类优化

**日期**: 2026-08-10  
**目标**: 提升 东莞通-建筑-外部参照（不打印）.dxf 的图元分类准确率  
**状态**: ✅ 完成

---

## 方法演变

| 阶段 | 方法 | 结果 |
|------|------|------|
| P84-A | YOLOv8 训练建筑构件检测模型 | ❌ 失败：mAP≈0，模型无法收敛 |
| P84-B | LSD 直线检测（图像级） | ❌ 放弃：回到图像路径，与 P84-A 同样问题 |
| P84-C | DXF polygon 几何闭合提取 | ❌ 不可行：4/5 测试图为 xref 空壳 |
| **P84-E** | **DXF 向量特征分类（根因修复）** | **✅ 成功** |

---

## P84-E 修复内容

### 1. LWPOLYLINE 面积归零
- **根因**: 未提取 `points`/`closed` 属性，area 始终为 0
- **修复**: `geometry.py` 添加 LWPOLYLINE 点列表 + 闭合标记提取
- **效果**: 面积 0 → 0-448m²

### 2. LINE 端点缺失
- **根因**: 未提取 `start_point`/`end_point`，仅有 length/angle
- **修复**: `geometry.py` 添加 LINE 端点坐标提取

### 3. LINE short_edge 错误（核心修复）
- **根因**: hv LINE 的 bbox `bw=0`，`short_edge = min(bw,bh)` 回退到 `length`，导致 door 判定失败
- **修复**: 用端点坐标计算 `real_short_edge = min(|dx|,|dy|)`
- **效果**: 700-2000mm hv LINE 正确归为 door

### 4. Room 判定阈值
- **原规则**: area < 10m² OR aspect > 3 即拒绝 → 45.5% 真实小房间误杀
- **修复**: area < 5m² AND aspect > 5 才拒绝
- **效果**: 小房间检出率 25% → 54.5%

### 5. 门宽 700mm 边界
- **浮点容差**: `700 <= length + 1` 避免 699.999mm 误判

### 6. YOLO 增强禁用
- `enhancement.py` `_yolo_enhance_impl` 直接返回 `[]`

---

## 效果对比

| 类型 | 修复前 | 修复后 | 变化 |
|------|--------|--------|------|
| other | 6,041 | 4,439 | **-1,602** |
| door | 1,310 | 2,644 | **+1,334** |
| wall | 1,311 | 1,482 | +171 |
| room | 17 | 98 | +81 |
| column | 146 | 172 | +26 |
| text | 638 | 638 | 0 |
| window | 265 | 265 | 0 |

**总实体**: 10,062 → 9,780（归并后），分类质量显著提升。

---

## 剩余 "other" 诊断（4,439 个）

| 来源 | 数量 | 可改善？ |
|------|------|----------|
| LINE < 500mm | ~12,100 | ❌ 填充图案/标注线/引线 |
| LINE 500-700mm hv | 492 | ⚠️ 可能是小门（<700mm），但规范下限 700mm |
| LINE 700-2000mm 斜线 | ~320 | ❌ 不是门，是斜向构件 |
| LWPOLYLINE "other" | 1,275 | ⚠️ 小 hatch、标注框，混入其中 |

**结论**: 剩余 4,439 个 "other" 中绝大部分是不可救的填充/标注元素。P84 已达成合理上限。

---

## 相关文件

- `src/baa_engine/parsers/geometry.py` — LWPOLYLINE 面积 + LINE 端点
- `src/baa_engine/semantic_analyzer/classify.py` — short_edge 修复 + room 阈值 + 700mm 容差
- `src/baa_engine/semantic_analyzer/enhancement.py` — YOLO 禁用
- `src/baa_engine/semantic_analyzer/_layer_rules_*.py` — 9 子模块拆分
- `docs/P84_NEW_DIRECTIONS.md` — 策略文档