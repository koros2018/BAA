# BAA 版本记录

## v2.5.79-stable (2026-09-11) — 当前
- HEAD: 54a8038
- P127: 天正 T3 降级管线主模块 + 42 单测 + 端到端扫描脚本
- P126: 前端单测落地（Vitest + utils.ts 27 用例）
- P128 Phase 1: TEXT/MTEXT 提取补齐（geometry.py extract_properties + compute_bbox）
- 修复: pdf_parser.py fitz 依赖声明（P99 矢量 PDF 管线此前无法运行 → 19 passed）
- 修复: requirements.txt 补 reportlab 运行时依赖（此前 6 个 test_p119 失败）
- 修复: DIM-002 测试误绕过撤回（3e79bf6 的错误诊断修正）
- ROADMAP: 新增 P135（T3 识别率验收闭环）、P136（扫描件 OCR，⛔ 阻塞）
- 测试: 2178 passed, 3 skipped, 0 failed（排除 test_p119_audit 文件缺失）

## v2.5.78-stable (2026-09-09) — 回退版
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
git checkout v2.5.78-stable   # 回退版（2026-09-09，P125 Phase 4 前端 bundle）
git checkout v2.5.79-stable   # 切回当前最新稳定版
git checkout v2.5.14-stable   # 更早历史回退版
```
