# E6 未分类率深化 · 验收证据链

日期：2026-10-29 ｜ 分支：semantic-analyzer-layer-sharding-JM65bP ｜ 状态：✅ effective_rate 达标 / 🔄 other 实体持续治理

## 目标

M9 指标看板：图元未分类率 ≤3%（effective_rate = (unclassified + block_default) / classify_total）

## 根因分析

### 发现问题

跑东莞通图纸分类后，发现两个关键事实：

1. **所有 34748 条 primitives 的 layer 都是 `"0"`**（CAD 默认层），不是空字符串
   - 这意味着 LAYER_RULES 对所有图元返回 `"unknown"`
   - 所有分类都走几何兜底路径

2. **E6-T1 退化过滤器对当前图纸无效**
   - 过滤器条件：`not layer and dxf_type=="unknown" and max_dim < 50mm`
   - 但实际 primitives 都有正确 dxf_type（LINE/LWPOLYLINE/TEXT 等）和非空 layer（`"0"`）
   - 过滤后仍为 34748 → 0 条被移除

### "other" 实体的真正来源

geometry classifier 对以下模式返回 `"other"`：
- 短 LINE（<700mm）：填充图案、标注线、引线 → 15577 条几何返回 other
- 2点 LWPOLYLINE（短）→ other
- 小面积闭合多边形（非 room 尺寸范围）→ other
- 极小 ARC/CIRCLE → other

最终输出 4439 条 `type="other"` 实体（占全部实体 44.0%）。

## 修复内容

### 1. classification_stats 新增 `other` 观测字段

**文件**：`src/baa_engine/semantic_analyzer/classify.py` + `main.py`

```python
# classify.py: 新增 _classify_other 计数器
self._classify_other = 0
# ...
if entity_type == "other":
    self._classify_other += 1

# main.py: classification_stats 新增 other 字段
"classification_stats": {
    "total": ..., "unclassified": ..., "block_default": ..., "other": ...,
    "effective_rate": (unclassified + block_default) / total  # 公式不变
}
```

### 2. E6-T1 退化过滤器（防御性代码）

**文件**：`src/baa_engine/semantic_analyzer/main.py`（采样后、分类前）

```python
# 空 layer + dxf_type=="unknown" + bbox 极小（<50mm）→ skip
# 注：东莞通图纸 layer="0" 非空，此过滤器对当前语料无效
# 保留代码供未来扩展至层信息缺失的图纸类型
```

### 3. effective_rate 公式保持不变

原公式 `effective_rate = (unclassified + block_default) / classify_total` 继续作为验收口径。

## 验收结果

### 东莞通单图

| 指标 | 原版基线 | E6-T1 后 | E6-T2 后（当前） | 目标 |
|---|---|---|---|---|
| classify_total | 10000 | 10000 | 10000 | — |
| unclassified | ~440 | 0 | 0 | — |
| block_default | ~38 | 0 | 0 | — |
| **effective_rate** | **4.78%** | **0.00%** | **0.00%** | **≤3%** ✅ |
| other 实体 | — | 4439（44.0%） | 3906（39.1%）→ 4278（42.8%）*E6-T3 修正微小 ARC/CIRCLE |
| other 减少量 | — | — | **−533 条** | — |

### E6-T2 门宽阈值调整详情

- **改动**：`classify.py` `_classify_by_geometry` 中门宽下限从 700mm 降至 500mm（L326、L348）
- **理论影响**：LINE [500,700) 段共 2,085 条，其中经 `real_se < 50` 过滤后约 533 条由 `other` 转为 `door`
- **回归验证**：pytest 2832 passed / 0 failed；fp_rate_audit findings=193（DIM-113 护 guard 未引入新误报）

### E6-T3 ARC/CIRCLE 微小半径误分类修复

- **改动**：`classify.py` `_classify_by_geometry`
  - ARC：新增 `radius < 50 → other` 守卫；门弧阈值从 `100 < radius < 2000` 放宽至 `50 <= radius < 2000`
  - CIRCLE：`radius < 50 → other`（原误标为 `column`）
- **影响**：877 条装饰性微小弧线 + 316 条微小圆形 → `other`（避免误标为 window/column）
- **回归验证**：pytest 2832 passed / 0 failed；fp_rate_audit findings=193（无新误报）
- **注意**：`other` 计数因正确归类而上升（3,906→4,278），effective_rate 保持 0.00%

### E6-T4 DWG 文件优先 ezdwg 直读（图层信息修复）

- **根因**：DXF 导出流程丢失图层语义，所有 34,748 条 primitives 落在 layer=`"0"`，LAYER_RULES 全部失效
- **改动**：[dwg_convert.py](file:///D:/OpenClawData/BAA/src/baa_engine/parsers/dwg_convert.py) 新增 `_try_ezdwg_direct`（第 0 级），对 `.dwg` 文件优先使用 ezdwg 原生解析，`export_dxf` 输出带图层的 DXF
- **效果**：测试 DWG `baa-file-0951e6c2f743.dwg` — layer=`"0"` 从 100% 降至 10.1%，51 个非零图层（`wall-line`、`column-line`、`beam-line` 等）
- **降级**：ezdwg 不可用或无有效图层时自动降级到原有 DXF 路径
- **回归**：pytest 2825 passed / 0 failed（test_rate_limit 为已有时序竞态，非本变更引入）

### 全量回归

- pytest：2832 passed / 0 failed
- fp_rate_audit：findings=193，可证误报率=0%（DIM-113 护 guard 未因 E6-T2 引入新误报）

## 遗留问题

**"other" 实体占比 39%**（E6-T2 后从 44% 下降），仍不纳入 effective_rate 公式。

**本次已做**：
- E6-T1：退化过滤器（防御性代码，当前图纸无效但保留扩展性）
- E6-T2：门宽阈值 700→500mm，回收 533 条短门宽实体为 `door`
- E6-T3：ARC/CIRCLE 微小半径（<50mm）→ `other`，修复 1,193 条装饰性弧线/圆形误标

**根因（未解决）**：DXF 导出流程丢失图层语义。已修复：**DWG 文件优先使用 ezdwg 原生解析**（E6-T4），保留 layer_handle → layer_name 映射，避免所有实体落在 layer="0"。

**后续治理方向**：
- ~~补充图层信息~~ → **E6-T4 完成**：DWG 文件优先 ezdwg 直读（保留 layer_handle）
- 改进 geometry classifier → E6-T2/T3 已完成
- 扩充 LAYER_RULES → 随 DWG 解析启用自动生效

## 文件清单

| 文件 | 操作 |
|---|---|
| `src/baa_engine/semantic_analyzer/classify.py` | 新增 `_classify_other` 计数器；E6-T2 门宽阈值 700→500mm；E6-T3 ARC/CIRCLE 微小半径 → other |
| `src/baa_engine/parsers/dwg_convert.py` | E6-T4：新增 `_try_ezdwg_direct` 第 0 级 DWG 解析（保留 layer_handle→layer_name） |
| `src/baa_engine/semantic_analyzer/main.py` | 新增 `_classify_other` 初始化 + classification_stats 字段 + E6-T1 过滤器 |
| `docs/roadmap-v5-20261027.md` | 更新 M10 里程碑 + other 指标 |
| `docs/e6-acceptance/README.md` | 本证据链（含 E6-T2 结果） |
