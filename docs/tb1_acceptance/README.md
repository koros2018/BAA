# T-B1 拓扑显式化证据链（B1a/B1b/B1c · 真实图纸验收）

> 关联：Roadmap v4 T-B1（G10 / B1）。基线 v2.5.79-stable 之后、M4（61ae4bf）之上。

## 一、交付物

| 模块 | 内容 |
|---|---|
| B1a | `src/baa_engine/semantic_analyzer/topology.py`：`build_topology_graph`（房间/门窗节点 + adjacent/contains 边）+ `topology_summary`（JSON 化：节点/边/邻接/连通分量） |
| B1b | `src/api/topology_routes.py`：`POST /api/v1/topology`（输入 entities 数组自包含，Bearer 认证），baa_api.py 注册 |
| 依赖 | requirements.txt 新增 `networkx>=3.0`（三同步：CI 清单同批更新） |

**设计决策（诚实记录）**：采用 `nx.Graph` 而非 DiGraph——空间邻接天然无向，summary 已双向列邻接满足判定层连通/邻接消费；疏散方向性语义属判定层，不在此臆造。护栏：只读消费实体，不触碰扫线法路径（room.py 零改动）。

## 二、过程真实缺陷修复

1. **stair 误入房间节点集**：A23 实测 579 个楼梯段（构件级）被计入房间节点，rooms=882 虚高 2.9 倍。已修复（`_ROOM_TYPES` 移除 `stair`，保留 `staircase` 楼梯间），修复后 A23 rooms=303。
2. 验收脚本 dict 传参缺陷（getattr 全 miss）——脚本级，已修。

## 三、B1c 验收结果（诚实上报：未达标）

条款「拓扑节点数与真实房间数偏差 ≤10%」**未达标**。

**修复后重测矩阵（同一张图、三种参考口径、三种偏差）**：

| 图纸 | 拓扑 rooms | 口径A 朴素文字计数 | 口径B 锚定文字（距检出房间≤2m） | 偏差A | 偏差B |
|---|---|---|---|---|---|
| A23云计算中心平面图 | 303 | 635 | 94 | -52% | +222% |
| 华为（深汕）A4建筑图 | 105 | 233 | 16 | -55% | +556% |

**双向噪声归因（不粉饰）**：
- 口径A 偏多：图例表/门窗表/索引中房间名重复计入。
- 口径B 循环依赖：锚定以检出房间为参照，漏检区域的房间名被系统性剔除——94/303 揭示**扫线检出区与命名区大面积错位**（大量检出房间无名、大量命名房间未检出）。
- 上游根因：扫线法房间召回不足（复合墙/柱网打断闭合）+ T3 墙线不进扫线（既有边界）；文字参考无位置真值。
- 结论：三种口径偏差互斥且均远超 ±10%，证明在无人工标注房间 GT 条件下该条款**不可判定**；根治依赖 T-A5 黄金标准 v2 建立房间 GT 后复测。本轮不通过调整阈值/臆造房间凑数（违反宁缺勿错与 DoD）。

## 四、已达标项

- **接口结构可被判定层消费**：节点/边/邻接表/连通分量全 JSON 化，12 个单测（含序列化、认证、非法输入、连通分量）验证。
- 全量回归 **2449 passed / 0 failed**（2437 + 12 新增）；room.py 扫线法路径零改动。

## 五、复现

```bash
pip install networkx>=3.0
python -m pytest src/tests/test_topology.py src/tests/test_topology_api.py -q
# 拓扑构建：analyze 结果 entities 中 type∈{room,corridor,staircase,fire_compartment,door*,window*}
# → build_topology_graph → topology_summary；API：POST /api/v1/topology {"entities":[...]}
```
