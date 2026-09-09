# BAA 最新路线图与开发指南 v2

> 2026-09-09 | 基于两份数据中心图纸方案（`tianzheng-mvp-data.html` / `engineering-drawing-loop.html`）对齐优化
> 当前 HEAD `e494cdd` = v2.5.78-stable
> 关联：`memory/archive/baa-architecture-2026-09-09-phase{1,2,3}.md`

## 0. 定位校准（必读）

两份方案的核心是**数据中心图纸 L1-L5 五层闭环**（正向解析→反向会意重构→量化验证），**不包含审查主路径**。BAA 的核心优势恰好是审查（49 ID / 390 原子函数 / 4459 规范行 / P107 EVAC BFS 闭环 / audit 工作流）。

**因此本路线图策略**：
1. **BAA 已有的能力不重做**（审查、扫线法、EVAC BFS、reverse_engine、PDF/DWG 兜底、大文件分页）
2. **补齐方案提出的真缺口**（天正 TCH 原生 / OCR / 拓扑显式化 / 合成数据完整管线 / IFC·STEP / YOLOv11 迁移 / 闭环量化）
3. **把闭环量化指标反哺审查质量**（Hausdorff / 图编辑距离可用于审查报告的证据链）
4. **不做无商业价值的项**（GNN 拓扑推理、VLM 端到端、数字孪生 3D Tiles 都在 6+ 月后）

---

## 1. 现状对齐矩阵

| 五层 | 方案要求 | BAA 现状 | 差距 | 优先级 |
|---|---|---|---|---|
| **L1 格式归一** | DWG→LibreDWG/ODA / DXF→ezdxf / PDF 矢量 / 天正 T3 | ezdxf 直连、DWG T3 六级兜底、PDF 矢量解析（P99/P100）| **天正原生 TCH 完全不支持** | 🔴 P127 |
| **L2 语义标注** | YOLOv11 + PaddleOCR + 尺寸关联 | YOLOv8m v6 mAP 0.572 + 尺寸解析 + 49 原子函数 | **无 OCR**、YOLOv11 未迁移 | 🔴 P128 / P129 |
| **L3 拓扑构建** | Shapely + NetworkX 显式拓扑图 | 扫线法+`_build_planar_graph` + EVAC BFS（P101/P105/P107）已内隐式实现 | 拓扑图未显式 NetworkX 化、无导出 API | 🟡 P130 |
| **L4 反向重构** | CadQuery→STEP / IfcOpenShell→IFC / 参数化 | `reverse_engine.py` 944 行 + `/api/v1/reverse` + `/reverse/export-dwg` | 只出 DXF/DWG，**无 IFC/STEP**、无 CadQuery | 🟡 P131 |
| **L5 闭环验证** | Hausdorff / 图编辑距离 / Git+DVC / 差异报告 | `validate_roundtrip` 自洽 + 审查违规清单 + 报告导出 | 无量化指标、无差异可视化 | 🔴 P132 |
| **数据合成** | CadQuery 参数化 + BIM→DXF + SynthPID 拓扑保持 + 噪声注入 | 合成图纸 626/626 检出 100% + `reverse_engine.py` MultiRoom | 无 YOLOv11 训练闭环、无合成→训练管线 | 🟡 P133 |
| **许可证** | AGPL/GPL 隔离为独立微服务 | YOLOv8 已在 AGPL 边缘、LibreDWG GPL | 未做隔离规划 | 🟢 P134 |

---

## 2. 近期（1-2 月）：v2.5.79-stable

**目标**：夯实质量基线 + 补 OCR 最小闭环 + 拓扑显式化

| P 项 | 名称 | 交付 | 验收 |
|---|---|---|---|
| **P126** | 前端组件单测 + Vitest 接入 | Vitest 配置 + Modal/ReviewTable/FilterBar/DrawingCanvas 关键组件单测 | ≥30 用例，覆盖率 ≥40% |
| **P127** | 天正 T3 降级管线（L1 补齐） | `tianzheng_t3.py`：图层名映射规则库（WALL$/WINDOW$/DOOR$/AXIS$ 等）+ XData 探测（多 AppID 尝试）+ 几何模式匹配（墙体平行线对 + 门窗 Block 名） | 5 张天正 T3 测试图：墙体识别 ≥80%、门窗 ≥75% |
| **P128** | OCR 集成（L2 补齐） | `ocr_pipeline.py`：DXF TEXT/MTEXT 直取（跳过 OCR）+ 扫描 PDF 走 PaddleOCR | 矢量文字提取率 100%、扫描件 OCR ≥85% |
| **P130** | 拓扑图 NetworkX 显式化（L3） | `topology_graph.py`：把 `_build_planar_graph` 输出转为 NetworkX DiGraph + `/api/v1/topology` 导出 API | 拓扑 JSON 输出，节点数与真实房间偏差 ≤10% |
| **P129** | YOLOv11 迁移学习（L2） | YOLOv11 替换 YOLOv8n，ArchCAD-400K 子集微调 10 类核心符号 | mAP50 ≥75%（10 类），本地 ONNX 部署 |

**里程碑**：v2.5.79-stable（P126 + P127 + P128 + P130 完成，P129 并行）

---

## 3. 中期（3-6 月）：v2.6.0

**目标**：真实客户 + 数据闭环 + IFC/STEP 输出

| P 项 | 名称 | 交付 | 验收 |
|---|---|---|---|
| **P113** | 真实用户试用与黄金标准扩库 | 5 家设计院/审图机构试用，黄金标准扩至 30+ 图纸 | 试用反馈闭环、A 级 ≥60% |
| **P112** | 协作前端 | 用户认证 + 团队空间 + 协作 UI（后端已完成） | 3 家真实团队上线 |
| **P131** | IFC/STEP 反向重构输出（L4） | `reverse_engine.py` 增加 IfcOpenShell 输出 IFC4 + CadQuery 输出 STEP | 5 张平面图 Hausdorff ≤2mm |
| **P132** | 闭环量化指标（L5） | `validation_metrics.py`：Hausdorff / 图编辑距离 / 语义匹配率 / 参数保真度 | 报告新增 4 项量化指标，闭环偏差 ≤5% |
| **P133** | 数据合成完整管线 | `synthetic_pipeline.py`：参数化生成 + 拓扑保持 + 样式随机化 + 噪声注入 | 合成 500 张 + 真实 300 张，YOLOv11 mAP50 ≥0.75 |
| **P116** | 报告产品化（封面/签字/审图机构视角） | 报告模板统一、多格式导出（PDF/HTML/JSON/Excel） | 报告无中文乱码、无空白章节 |
| **P115** | 云端部署流水线 | GitHub Actions → Docker → 云主机，一键部署 | 云主机生产就绪 |

**里程碑**：v2.6.0（P113 客户验证 + P131/P132 闭环上线）

---

## 4. 长期（6-12 月）：v3.0

**目标**：产品化 + 生态

| P 项 | 名称 | 交付 |
|---|---|---|
| **P117** | 知识库开放 | 原子函数/规范 JSON schema + 版本化发布 + SDK 示例（10 分钟跑通） |
| **P118** | 商业模式验证 | 1 页产品定位 + 1 页定价表 + 3 个客户试用计划（依赖 P113 数据） |
| **P134** | 许可证合规隔离 | AGPL（YOLOv11/PyMuPDF）隔离为独立微服务，GPL（LibreDWG）独立进程调用 |
| 云端多模态集成 | 云端大模型（商量多模态/GPT-4V）做整体语义审查，本地 YOLO 做局部图元 | 混合架构上线 |
| 数字孪生 | IFC→3D Tiles→WebGL（依赖 P131） | 可选模块，非核心 |

**里程碑**：v3.0（SaaS 上线 + SDK 开源 + 多模态混合审查）

---

## 5. 风险与决策

### 5.1 关键决策（需 Master 拍板）

| # | 决策 | 推荐 | 理由 |
|---|---|---|---|
| 1 | 部署路线 | 私有部署优先，SaaS 半年后再评估 | 数据中心图纸敏感，客户偏好私有 |
| 2 | 商业路线 | 核心收费 + 文档/SDK 开源引流 | 与 P113 试用定位匹配 |
| 3 | 模型路线 | YOLOv11 主力（P129）+ 云端多模态辅助 | 数据闭环可控、成本可控 |
| 4 | 规范范围 | GB 为主 + NFPA 参照扩展 | BAA 优势在 GB，NFPA 已有 329 行基础 |

### 5.2 高风险项

| 风险 | 缓解 |
|---|---|
| 天正 T3 导出依赖客户端环境（Windows + 天正 + AutoCAD）| 提供 AutoLISP 脚本 + pywin32 自动化方案，同时保留"提交前 T3 导出"手动流程 |
| PaddleOCR 中文识别在低清扫描件上准确率波动 | P128 验收以 ≥200DPI 为基线，低清走 VLM 兜底（后期） |
| IfcOpenShell 与现有 DXF 输出链路冲突 | P131 独立文件 `reverse_engine_ifc.py`，不修改主链路 |
| AGPL 传染（LibreDWG / YOLOv11）| P134 优先做合规规划，避免后期重构 |

---

## 6. 与旧 roadmap 的差异（重要）

- **新增 P127-P134** 共 8 项，聚焦补齐两份方案提出的 L1-L5 缺口
- **P111 保持终止**（Phase 2 结论：v2 18 类 mAP50=0.001 证伪），改由 P129 YOLOv11 迁移学习重启
- **P113/P116/P115** 从"可启动/后续"提到中期主线
- **P112 协作前端** 保持进行中（后端已完成）
- **不做** GNN 拓扑推理、VLM 端到端、扩散模型 CAD 生成、数字孪生 3D Tiles（远期候选）

---

## 7. 立即执行

**当前会话**：启动 P126（前端单测）作为 v2.5.79 起点

**下一批**：P127（天正 T3）+ P128（OCR）并行（都是 L1/L2 补齐，独立）

**中期主线**：P113（客户试用）+ P132（闭环量化）并行
