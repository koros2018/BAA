# T-A2 块语义分类 · 收口复测证据链

> 复测日期：2026-10-20（阶段 A/B 收口）· 引擎 v2.5.80-stable（383207b，含 M1–M4 分类治理）
> 脚本：`src/tools/ta2_real_drawing_acceptance.py` · 语料：40 张真实图纸（D:\BaiduNetdiskDownload\测试图纸）
> 证据：`ta2_rerun_20261020.json`（逐图纸 ID + 命中块名 + ATTRIB 样本 + 前后对比）

## 口径修正（本次复测关键变更）

原脚本 baseline 仅屏蔽 `classify_block_name`（V1）与 `lookup_legend`；M4 图例学习器
（Step 0.9 预扫描，走 `classify.py` L655 `_legend_learned` 独立路径）未被屏蔽，会人为
抬高基线。本次在 baseline 分支补第三补丁 `legend_learner._learn_legend_blocks → {}`，
基线口径 = 纯 pre-T-A2（V1 规则 + 无图例 + 无学习器）。

实测 M4 学习器在本语料贡献极小（基线 block_default 728→726，Δ=2），复测结论与旧记录
方向一致，修正不改变判定。

## 复测结果（40 张 / 33887 图元）

| 指标 | 基线(pre-T-A2) | 现状(v2.5.80) | 变化 |
| --- | --- | --- | --- |
| 有效未分类率 (unclassified+block_default)/total | 5.63% | 4.78% | **相对 -15.1%** |
| block_default（INSERT 未覆盖回退 wall） | 726 | 438 | **-39.7%**（288 块重归类） |
| 回归（实体丢失/劣化） | — | — | **0** |
| 守卫摘除 / 其他类型变化 | — | — | 0 / 0 |

命中样例：发电机/两绕组变压器 wall→equipment（西安特发数据中心）、办公网网络点/语音点
wall→telecom_point（山东斐讯弱电）、智能照明控制面板 wall→equipment 等。

## 验收判定

1. **图元未分类率相较基线下降 ≥50% — 未达标（15.1% < 50%）· 诚实上报**。
   归因：块语义机制只触达 INSERT 图元；本语料残量未分类主体为**非 INSERT 图元**
   （未映射图层上的 LINE/TEXT 等被判 unknown），块名/图例机制结构性触达不了。
   机制本身有效（INSERT 覆盖提升 -39.7%），继续收窄需 M 系列式图层规则扩面而非块语义。
   注：绝对值 4.78% 已低于指标看板 3 月目标 ≤7%（不同语料口径不可直接混比，仅作参考）。
2. **映射命中案例出具前后对比证据链 — 达标**：JSON 逐图纸记录 drawing_id + block_names
   分布 + 命中明细（block='块名' attribs=[...] wall→类型）。
3. **联合 LAYER_RULES 后不引入新增误报 — 达标**：regressions=0、guard_removed=0、
   changes=0（回归门：仅实体丢失/劣化为块语义回退计失败）。
