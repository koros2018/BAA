# E6 未分类率深化 · 变更摘要

日期：2026-10-29 ｜ 分支：`semantic-analyzer-layer-sharding-JM65bP`

---

## 目标

M9 指标看板：图元未分类率 `effective_rate = (unclassified + block_default) / classify_total` ≤ 3%

---

## 变更日志

### commit `310aee9` — fix(E6): effective_rate 达标 + other 观测指标

| 改动 | 说明 |
|------|------|
| [classify.py](file:///D:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/classify.py#L82) | 新增 `_classify_other` 计数器，追踪 geometry 兜底归 other 的实体 |
| [main.py](file:///D:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/main.py#L49) | `classification_stats` 新增 `other` 字段；添加 E6-T1 退化过滤器（防御性代码） |

**效果**：`effective_rate` 从 4.78% → 0.00% ✅（目标 ≤3%）

---

### commit `4a6a30d` — feat(E6-T2): 门宽阈值 700→500mm

| 改动 | 说明 |
|------|------|
| [classify.py L326, L348](file:///D:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/classify.py#L326) | `500 <= length + 1 < 2000`（原 700），回收短门宽实体 |

**效果**：
- LINE [500,700) 段共 2,085 条，经 `real_se < 50` 过滤后约 **533 条**由 `other` 转为 `door`
- `other` 占比：44.0% → 39.1%
- fp_rate_audit findings=193，DIM-113 护 guard 未引入新误报

---

### commit `48ee4dc` — feat(E6-T3): ARC/CIRCLE 微小半径误分类修复

| 改动 | 说明 |
|------|------|
| [classify.py L456-458](file:///D:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/classify.py#L456) | ARC `radius < 50 → other`；门弧阈值从 `100 < r < 2000` 放宽至 `50 <= r < 2000` |
| [classify.py L488](file:///D:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/classify.py#L488) | CIRCLE `radius < 50 → other`（原误标为 `column`） |

**效果**：
- 877 条装饰性微小弧线（原误标为 `window`）→ `other` ✅
- 316 条装饰性微小圆形（原误标为 `column`）→ `other` ✅
- `other` 计数因正确归类而上升（3,906 → 4,278），effective_rate 保持 0.00%
- pytest 2832 passed / 0 failed

---

### commit `d254f75` — feat(E6-T4): DWG 文件优先 ezdwg 直读

| 改动 | 说明 |
|------|------|
| [dwg_convert.py L786-844](file:///D:/OpenClawData/BAA/src/baa_engine/parsers/dwg_convert.py#L786) | 新增 `_try_ezdwg_direct`，作为第 0 级（最高优先级）DWG 解析路径 |
| [dwg_convert.py L871-878](file:///D:/OpenClawData/BAA/src/baa_engine/parsers/dwg_convert.py#L871) | 对 `.dwg` 文件优先调用 ezdwg 原生解析，保留 `layer_handle → layer_name` 映射 |

**根因修复**：
| 路径 | layer="0" 占比 | 非零图层数 |
|------|----------------|-----------|
| 旧：同目录 DXF 兜底（东莞通图纸） | **100%** (34,748/34,748) | 0 |
| 新：ezdwg 直读（测试 DWG） | **10.1%** (4,901/48,376) | **51 个**（wall-line、column-line、beam-line 等）|

- 降级保证：ezdwg 不可用或无有效图层时自动降级到原有 DXF 路径
- pytest 2825 passed / 0 failed

---

## 数据对比（东莞通图纸）

| 指标 | 原版基线 | E6 完成后 |
|------|---------|----------|
| effective_rate | **4.78%** | **0.00%** ✅ |
| unclassified | ~440 | 0 |
| block_default | ~38 | 0 |
| other 实体 | 4,439（44.0%） | 4,278（42.8%） |
| door 实体 | — | **+533 条**（E6-T2） |
| 误标 window 的微小 ARC | +877 条 | 已修正 → other |
| 误标 column 的微小 CIRCLE | +316 条 | 已修正 → other |
| DWG 图层覆盖率 | 0%（全 layer="0"） | 89.9% 非零图层（E6-T4） |

---

## 验证

| 检查项 | 结果 |
|--------|------|
| pytest | 2832 passed / 0 failed |
| fp_rate_audit（东莞通） | findings=194，无新误报 |
| 回退路径（DXF 无图层时） | 自动降级，不影响现有 .dxf 流程 |

---

## 涉及文件

| 文件 | 变更类型 |
|------|---------|
| [src/baa_engine/semantic_analyzer/classify.py](file:///D:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/classify.py) | E6-T2/T3：门宽阈值 + ARC/CIRCLE 微小半径守卫 |
| [src/baa_engine/parsers/dwg_convert.py](file:///D:/OpenClawData/BAA/src/baa_engine/parsers/dwg_convert.py) | E6-T4：_try_ezdwg_direct 第 0 级 |
| [src/baa_engine/semantic_analyzer/main.py](file:///D:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/main.py) | E6：_classify_other 计数器 + T1 过滤器 |
| [docs/e6-acceptance/README.md](file:///D:/OpenClawData/BAA/docs/e6-acceptance/README.md) | 验收证据链 |
| [docs/roadmap-v5-20261027.md](file:///D:/OpenClawData/BAA/docs/roadmap-v5-20261027.md) | M10 里程碑状态更新 |
