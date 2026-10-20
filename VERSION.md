# BAA 版本记录

## v2.5.80-stable (2026-10-20) — 当前
- HEAD: c0c6f16
- T-B6: 工作流闭环（rectifying/rechecking 状态机 + 白名单流转校验、整改记录表 + 3 端点、复查端点 findings 差集对比）+ 违规↔图元双向定位（/render/{id}/interactive + bbox IoU≥0.3 回退），E2E 12/12、单测 21/21
- T-B5: 协作前端收尾（认证/团队/评论/审批全流程 E2E 10/10）+ 修复 E2E 技术债 TD-E2E-003/004
- T-B4: 报告产品化（PDF 条款索引/审查结论/签署归档页 + HTML/XLSX 导出，严重度枚举统一 critical/major/minor）
- T-B3: recall 指标管线（分类 FN/recall 对账 + history.jsonl + CI recall gate；opening_micro recall 0.9796 → 1.0）
- T-B2: 聚合作用域（EXIST 误报 critical 465 → 0）
- T-B1: 拓扑显式化（NetworkX 房间邻接图 + /api/v1/topology）
- M1–M4: 语义层分类治理 + M4 图例学习器（块名无判别信号根治，dimable 缺失率 -4.45pp）
- T-A4: 属性抽取补齐
- 治理: fire_compartment 分类规则落地 + T3 标记图元采样豁免（组件层已识别实体不再被随机丢弃）
- P137: 数据训练管线（人工审核 UI + 统一 CLI 入口 + 数据集资产盘点脚本）
- 修复: T3 代理实体漏数 + 矩形柱分解态识别；CI JS 检查逻辑修正；black 全仓 lint 重排
- 测试: 2505 passed, 14 skipped, 0 failed（零排除）

## v2.5.79-stable (2026-09-11) — 回退版
- HEAD: 9f480ef
- P127: 天正 T3 降级管线主模块 + 42 单测 + 端到端扫描脚本
- P126: 前端单测落地（Vitest + utils.ts 27 用例）
- P128 Phase 1: TEXT/MTEXT 提取补齐（geometry.py extract_properties + compute_bbox）
- 修复: pdf_parser.py fitz 依赖声明（P99 矢量 PDF 管线此前无法运行 → 19 passed）
- 修复: requirements.txt 补 reportlab 运行时依赖（此前 6 个 test_p119 失败）
- 修复: DIM-002 测试误绕过撤回（3e79bf6 的错误诊断修正）
- 修复: test_p119_audit 路径迁移至 ts/components/audit.ts（f068fe6 删除 js/ 后长期 collection error）
- ROADMAP: 新增 P135（T3 识别率验收闭环）、P136（扫描件 OCR，⛔ 阻塞）
- 测试: 2224 passed, 3 skipped, 0 failed（零排除）

## v2.5.78-stable (2026-09-09) — 历史稳定版
- HEAD: be3052d
- P125 Phase 4: bundle 可读化 + sourcemap

## v2.5.19-stable (2026-07-25) — 历史稳定版
- HEAD: 0071de5
- P70 全覆盖: 340/340 实体类型, 1198/1198 refs (100%)
- P71 误报修复: DIST-001 疏散距离不再误用 floor.length
- YOLOv8m v6 集成: 裁剪渲染 + conf 0.15 + 路径优先级更新 (mAP50=0.572)
- 真实图纸基线同步: column/text/fire_hydrant/sprinkler/fire_extinguisher 漂移修正
- 测试: 1975/1975 全通过

## v2.5.15-stable (2026-07-24) — 上一稳定版
- HEAD: aa5179b
- P70 全覆盖: 340/340 实体类型, 1198/1198 refs (100%)
- P70 误报修复: FAIL 从 8659 (14.9%) → 545 (1.1%), 减少 93.7%
- 修复: EXIST-052/083/093 系统性误报 (requires_global_context)
- 修复: _classify_by_geometry 两处未定义变量

## v2.5.14-stable (2026-07-21) — 回退版
- HEAD: bed126e
- P58-P62 功能完整
- P69 PDF 后端已完成
- 实体覆盖: 289/345 (P70 之前状态)

## 回退操作
```bash
git checkout v2.5.79-stable   # 回退版（2026-09-11，P127 T3 管线 + P126 前端单测）
git checkout v2.5.80-stable   # 切回当前最新稳定版
git checkout v2.5.14-stable   # 更早历史回退版
```
