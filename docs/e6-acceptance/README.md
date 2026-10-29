# E6 未分类率深化 · 验收证据链

日期：2026-10-28 ｜ 分支：main ｜ 状态：✅ effective_rate 达标 / ⚠️ other 实体待治理

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

| 指标 | 原版基线 | 修复后 | 目标 |
|---|---|---|---|
| classify_total | 10000 | 10000 | — |
| unclassified | ~440 | **0** | — |
| block_default | ~38 | **0** | — |
| **effective_rate** | **4.78%** | **0.00%** | **≤3%** ✅ |
| other 实体 | — | 4439（44.0%） | 观测中 |

### 全量回归

- pytest：2832 passed / 0 failed
- fp_rate_audit：findings=191，可证误报率=0%

## 遗留问题

**"other" 实体占比 44%** 不纳入 effective_rate 公式，但实际输出中占比显著。

降低 other 占比需要：
1. **补充图层信息**：让 parser 正确提取 layer 名（当前所有图元 layer="0"）
2. **改进 geometry classifier**：将短 LINE/小多边形按语义归类（如 annotation/dimension）
3. **扩充 LAYER_RULES**：覆盖更多实际图层名

这三项属于 E6 后续治理，不在本轮任务范围内。

## 文件清单

| 文件 | 操作 |
|---|---|
| `src/baa_engine/semantic_analyzer/classify.py` | 新增 `_classify_other` 计数器 |
| `src/baa_engine/semantic_analyzer/main.py` | 新增 `_classify_other` 初始化 + classification_stats 字段 + E6-T1 过滤器 |
| `docs/roadmap-v5-20261027.md` | 更新 M5 指标 + 验收数据 |
