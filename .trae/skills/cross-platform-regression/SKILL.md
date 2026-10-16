---
name: cross-platform-regression
description: 跨平台兼容验证方法论。当改动涉及系统路径、外部进程调用（soffice 等）、字体、文件编码、可选依赖，或修复 CI 跨平台失败时使用。不适用于纯算法或纯前端改动。
---

# 跨平台兼容验证方法论

源自 2026-10-15 Windows/macOS 修复 13 个失败 + CI 治理的完整经验。

## 核心原则

**仅在单一操作系统验证的代码必然存在跨平台缺陷。** 所有涉及系统交互的改动必须通过 Windows / Linux / macOS 三平台验证。

## 高频缺陷模式与对策

| 模式 | 错误做法 | 正确做法 |
|------|---------|---------|
| 外部进程探测 | Unix `which` 命令 | `shutil.which()`（跨平台） |
| 安装路径探测 | 仅查 PATH | 三级：环境变量优先 → PATH → 平台常见安装路径兜底（Windows 查 Program Files） |
| CJK 字体 | 仅 Linux 路径（wqy） | 候选列表含 Windows（msyh.ttc/simhei.ttf）+ macOS（Songti/STHeiti/Arial Unicode） |
| macOS 字体 | 直接用 PingFang/Hiragino | 它们是 CFF 轮廓，reportlab TTFont 不支持；TrueType 优先 + 逐候选 try/except 容错，CFF 降为末位 |
| 可选依赖 | 不声明，靠运行时降级 | 核心依赖必须进 requirements.txt；降级路径必须在 CI 以"已装/未装"两种形态各跑一遍 |
| import 作用域 | 依赖外层/调用方 import | 每个函数/闭包自己 import（P73 闭包 NameError、F3 shutil 作用域教训） |

## 验证清单（改动涉及上述场景时逐项打勾）

- [ ] Windows 本机全量：`python -m pytest -q`（基线 2246 passed / 14 skipped / 0 failed）
- [ ] 真实图纸基线：`pytest -m real_drawing src/tests/test_real_drawings.py -q`（8 passed）
- [ ] Linux CI：`python scripts/linux_ci_regression.py`（阶段 0-5；`--probes-only` 秒级自检）
- [ ] macOS：CI `macos_compatibility` job 或实机验证
- [ ] 新增探测逻辑配套封闭单元测试（monkeypatch 平台属性 + 临时目录重定向系统路径，不依赖本机环境）
- [ ] requirements.txt、CI 环境、跨平台清单三处同步更新

## 已知环境陷阱速查

- `BAA_PDF_FONT` 指向不存在路径时直接 RuntimeError，不回退候选列表（by design）
- CI 环境 data/files 只有合成 DXF——不能用该目录文件数判定基线图纸在场（API 上传测试会写入合成文件造成假阳性）；依赖固定基线图纸的 job 缺图时应 SKIP + notice，不是 FAIL
- LibreOffice 大概率无 DWG 导出 filter；DXF→DWG 备选 ODA File Converter
- Linux 跑 PDF 测试组需 `fonts-wqy-zenhei`

参考文档：`docs/cross-platform-checklist-20261015.md`。
