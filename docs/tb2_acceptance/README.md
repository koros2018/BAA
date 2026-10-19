# T-B2 聚合作用域证据链（B2a/B2b/B2c · 真实图纸验收）

> 关联：Roadmap v4 T-B2（B2）。基线 T-B1（e290e46）之上。验收：EXIST 误报率下降 ≥80% + 不引入漏报。

## 一、交付物

| 模块 | 内容 |
|---|---|
| B2a | `src/baa_engine/scope_aggregator.py`：`build_scopes`（fire_compartment 分区优先，回退 50m 网格；全实体铺格）+ `aggregate_exist_in_scopes`（pass/partial/missing/no_scopes + missing_scopes 清单），15 单测 |
| B2b | 挂接 3 处：review_routes 主链路 + batch_routes 两处（共享 `_run_exist_scope_batch` helper）；render_routes 仅展示不产生 finding，不改 |
| 定版判定语义 | pass → 无 finding；partial → **low**（区域提示：N/M 个作用域未检出）；missing → critical FAIL（真缺失，语义与旧等价） |

## 二、过程真实缺陷修复（量化暴露）

1. **目标实体铺格恒 pass**：v1 `include_types=targets` 让目标实体「既当尺子又当考生」——网格由目标实体铺成 → 每格天然命中 → 465/465 次对比全部 pass，判定形同虚设。修正：全实体铺格（空间结构基准），目标实体仅归属统计。
2. **主链路死代码**：旧 review_routes EXIST 缺失检查 `any(func.matches(e))` 中 matches 即类型判断，预过滤已保证交集非空 → has_match 恒 True → 缺失 finding 从不产生。B2b 挂接后该链路恢复预期功能。
3. **盲判误报主通道**：`execute_missing_batch` 交集非空即 `execute(None)`——不看实体，图中类型明明存在仍判缺失。这是 EXIST 误报的唯一活跃来源。

## 三、B2c 量化结果（30 张抽样，465 次函数对比）

| 指标 | OLD_batch（盲判） | NEW（聚合定版） |
|---|---|---|
| critical FAIL | 465 | **0** |
| low 区域提示 | 0 | 447 |
| 确认全作用域覆盖（pass） | 0 | 18 |
| 真缺失（missing） | 0 | 0 |

- **critical FAIL 下降 100%**（≥80% 达标）。诚实解读：OLD 的 465 个 critical 在本抽样中 100% 属误报（类型在图中存在却被判缺），NEW 全部修正——447 降级为带「N/M 个作用域未检出」的 low 提示、18 确认覆盖。
- **漏报保护**：missing 判定语义与 OLD 等价（全图无目标类型才 critical）；抽样 missing=0，构造上不存在「OLD 报 NEW 不报」路径（pass 要求全作用域命中，partial 仍可见）。
- 局限（诚实）：网格（50m）≠防火分区，partial→low 是 v1 务实语义；~~分区识别落地后提升~~ → **已落地（2026-10-19 治理①）**：A-FIRE/防火分区图层闭合区域产 fire_compartment/fire_zone，底图实测 grid 90 格→compartment 3 分区（docs/governance_20261019/）。

## 四、复现

```bash
python -m pytest src/tests/test_scope_aggregator.py -q          # 15 单测
python -m pytest src/tests -q                                    # 全量 2464 passed
# 量化脚本（临时，不入库）：30 张抽样 × old_batch 盲判 vs new 聚合对比
# 口径：critical FAIL 数 + missing 漏报保护（missing_total == new_critical）
```
