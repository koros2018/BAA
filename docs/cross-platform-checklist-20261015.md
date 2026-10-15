hos# 跨平台验证清单 —— Windows 兼容性修复（2026-10-15）

> 背景：2026-10-15 全量测试套件（`pytest -q`）暴露 13 个失败，根因均为代码仅在 Linux
> 环境验证过、Windows 可移植性未打通。修复后全量套件 **2240 passed / 0 failed**（Windows
> 本机，Python 3.13.12 / pytest 9.0.3 / ezdxf 1.4.3 / reportlab 4.x / pytest-asyncio 1.4.0）。
> 本清单固化每个修复点的跨平台验证状态，供 CI 与其他平台补验使用。
>
> **后续演进（同日）**：soffice 探测增强落地（+6 探测单测、+1 skipif 冒烟测试；
> pytest-asyncio 装回的 22 个异步用例已含在 2240 内）→ 当前全量基线
> **2246 passed / 14 skipped / 0 failed**。
> Linux CI 统一走验证脚本：`python scripts/linux_ci_regression.py`（详见下方"回归命令"）。
> **DWG 解析就绪（同日）**：ezdwg 0.16.0 装入 + DWG 链路 4 缺陷修复，
> `requirements.txt` 已纳入 ezdwg（详见下方"DWG 原生解析就绪状态"）。

## 修复点一览

| # | 文件 | 缺陷 | 修复 |
|---|---|---|---|
| F1 | `src/baa_engine/report_generator/components.py` `ensure_font()` | CJK 字体候选仅含 Linux 路径，Windows 必抛 `RuntimeError` | 候选列表追加 `C:/Windows/Fonts/msyh.ttc`、`simhei.ttf`、`simsun.ttc` |
| F2 | `src/baa_engine/reverse_engine.py` `_export_via_libreoffice()` | 用 Unix `which` 命令探测 soffice，Windows 抛 `FileNotFoundError`，DXF 降级分支不可达 | 改用跨平台 `shutil.which` |
| F3 | `src/baa_engine/reverse_engine.py` `_export_via_libreoffice()` | `shutil.copy2` 在 LibreOffice 成功路径上 `NameError`（`shutil` 仅在调用方方法体导入） | 作用域内补 `import shutil` |
| F4 | `src/api/baa_api.py` deconstruct 端点 | `yolo_entities` 仅在 `load_model()` 成功时绑定，YOLO 失败被吞后 L826 读未绑定变量 → 端点 500 | 预绑定 `yolo_entities: list = []`（健壮性修复，非平台相关，一并纳入回归） |

## F1 CJK 字体解析

| 平台 | 前置条件 | 预期行为 | 验证方式 | 状态 |
|---|---|---|---|---|
| Windows | 无 `BAA_PDF_FONT` | 命中 `msyh.ttc`（TTC subfontIndex=0），注册名仍为 `WQY` | `pytest src/tests/test_pdf_report.py src/tests/test_p119_correction_notice.py -q` | 已验证（18 passed，2026-10-15） |
| Windows | `BAA_PDF_FONT` 指向有效 ttf/ttc | 环境变量优先，不扫候选列表 | 同上，env 设为 `simhei.ttf` | 已验证（1 passed，2026-10-15） |
| Windows | `BAA_PDF_FONT` 指向不存在路径 | **直接 RuntimeError，不回退候选列表**（`if not ttf_path` 才扫描） | 同上，env 设为不存在路径 | 已验证（RuntimeError 复现，2026-10-15） |
| Linux | 有 wqy-zenhei / NotoCJK | 候选列表前 5 项不变，行为与修复前一致 | Linux CI 全量 `pytest -q` | 待验证（CI 回归）；脚本阶段 1/2 已就绪 |
| macOS | 默认 | ~~候选列表无 macOS 字体~~ 候选已补齐（PingFang / Hiragino / Songti，2026-10-15），Windows 回归不受影响 | macOS 实机 `pytest test_pdf_report.py test_p119_correction_notice.py -q` | 已实施；macOS 实机回归待做 |
| 全平台 | TTC 注册 | reportlab `TTFont` 读 TTC 首个子字体；`WQY` 与 `WQY-Bold` 注册同一文件，粗体为伪粗体 | 视觉抽检 PDF 中文粗体 | 已知既有行为，非回归项 |

## F2+F3 LibreOffice 探测与 DWG 导出

| 平台 | 前置条件 | 预期行为 | 验证方式 | 状态 |
|---|---|---|---|---|
| Windows | 无 soffice/libreoffice | `shutil.which` 返回 None → 优雅降级返回 DXF 路径 | `pytest src/tests/test_reverse_roundtrip.py -q` | 已验证（17 passed，2026-10-15） |
| Windows | 有 LibreOffice（在 PATH） | `shutil.which` 命中 → headless 转换 → `shutil.copy2` 拷贝 .dwg；冒烟测试 `test_export_dwg_with_libreoffice`（skipif 门控）已就位 | 装 LibreOffice 后跑 `test_reverse_roundtrip.py` | 待验证（本机无 LibreOffice） |
| Linux | 有 soffice | 修复前 `which` 命中、行为不变；注意 F3 使成功路径首次真正可用；冒烟测试同上可覆盖 | Linux CI + LibreOffice 环境 | 待验证（F3 成功路径此前从未实际执行过） |
| Linux | 无 soffice | 修复前 `which` rc!=0 → return False；现在 `shutil.which` 返回 None → return False，语义一致 | Linux CI 全量 | 待验证（CI 回归）；脚本阶段 3 已就绪（降级探针） |
| 全平台 | soffice 已装但不在 PATH | 处置方案 C 已实施（2026-10-15）：`BAA_SOFFICE_PATH` env 优先 → PATH → Windows 常见安装路径兜底；探测逻辑 6 个单测覆盖（`test_reverse_roundtrip.py::TestSofficeDetection`） | 未装环境回归 + env 回退探针 + 6 个探测单测 | 已实施（17+6 passed）；有 LibreOffice 环境待验 |

## F4 yolo_entities 预绑定

| 前置条件 | 预期行为 | 验证方式 | 状态 |
|---|---|---|---|
| `use_yolo=True` 且 YOLO 模型/依赖缺失 | 端点 200，`yolo_entities=0`、`yolo_enabled=true`，主流程不受影响 | `pytest src/tests/test_review_routes.py -q` | 已验证（2026-10-15） |
| `use_yolo=True` 且 `load_model()` 返回 False | 同上（同一未绑定路径） | 同上 | 已验证 |
| YOLO 正常出结果 | `yolo_entities` 反映实际合并数 | 需 YOLO 模型权重环境 | 待验证 |

## DWG 原生解析就绪状态（2026-10-15）

ezdwg 0.16.0 安装后首次真正执行 DWG 链路，暴露 4 个被"ezdwg 未安装"警告长期掩盖的
潜伏缺陷，已全部修复（commit `a329209`，均在 `parsers/dwg_convert.py`）：

| # | 缺陷 | 后果 |
|---|---|---|
| D1 | `_parse_dwg(self, path)` / `_try_ezdwg_export_dxf(self, path)` 签名残留 `self`（方法化拆分遗留） | `drawing_parser` 按独立函数调用必 TypeError，**DWG 解析此前完全不可用** |
| D2 | 3 处 `except as _e` 日志误引用未绑定 `e`（xref ×2 + 块展开） | 异常时 NameError 掩盖真实错误 |
| D3 | 模块无 `import ezdxf`，9 处 `ezdxf.*` 依赖调用方命名空间 | 独立调用必 NameError，第 5 级 raw 解码全灭 |
| D4 | — | 依赖声明缺失：`ezdwg>=0.16.0` 已加入 `requirements.txt` 核心依赖组 |

| 环境 | 状态 | 说明 |
|---|---|---|
| Windows 本机 | **已就绪** | ezdwg 0.16.0（win_amd64 wheel）+ 4 缺陷修复；服务启动日志零 P120 警告 |
| Linux CI | **已就绪（随 requirements 分发）** | CI 全量与新 `cross_platform_regression` job 自动安装；仓库无 DWG 数据，CI 仅验证导入与降级路径 |
| macOS | 待验证 | 需确认 ezdwg 是否发布 macOS wheel；缺失时代码优雅降级（P120 提示），不影响 DXF 主流程 |

**端到端验证**（`data/files` 真实 DWG，Windows 本机）：AC1018 → 48376 图元、AC1015 → 4182、
AC1021 → 41368，全部解析成功；全量回归 2246 passed 不变。

## 回归命令

### Windows 本机基准

```powershell
# 全量（默认排除 slow / real_drawing）
D:\APPstore\miniconda3\python.exe -m pytest -q
# 预期: 2246 passed, 14 skipped, 0 failed

# 真实图纸基线（CI 独立阶段）
D:\APPstore\miniconda3\python.exe -m pytest -m real_drawing src/tests/test_real_drawings.py -q
# 预期: 8 passed

# 定向回归（本次修复涉及面）
D:\APPstore\miniconda3\python.exe -m pytest src/tests/test_pdf_report.py src/tests/test_p119_correction_notice.py src/tests/test_reverse_roundtrip.py src/tests/test_review_routes.py -q
# 预期: 全绿
```

### Linux CI（验证脚本 —— 已就绪，2026-10-15）

```bash
# 全阶段（0 环境自检 / 1 F1 静态漂移 / 2 F1 字体运行时 / 3 F2 语义 / 4 全量回归 / 5 real_drawing 基线）
python scripts/linux_ci_regression.py

# 快速漂移自检（跳过阶段 4/5 的 pytest，秒级）
python scripts/linux_ci_regression.py --probes-only

# 退出码: 0 = 全部必选阶段通过；1 = 存在漂移
# 环境相关 SKIP（非失败）: 阶段 2 无 CJK 字体 → apt-get install -y fonts-wqy-zenhei；
#                          阶段 5 data/ 无图纸 → 需配置图纸数据源
# Windows 本机试运行: 8/8 PASS（2026-10-15，探针跨平台有效，可作非 Linux 平台的漂移自检）
```

## 已知空白处置方案

### 空白 A：macOS 字体候选缺失

**验证步骤**（在 macOS 机器上执行）：

```bash
# 1. 复现失败（确认空白真实存在）
python -m pytest src/tests/test_pdf_report.py::TestReportGenerator::test_generate_minimal -q
#    预期: RuntimeError: CJK font not found at None

# 2. 用系统字体临时绕过，验证 reportlab 能否注册 PingFang.ttc
export BAA_PDF_FONT="/System/Library/Fonts/PingFang.ttc"
python -m pytest src/tests/test_pdf_report.py src/tests/test_p119_correction_notice.py -q
#    预期: 全绿 → 证明补候选即可解决，无需换字体方案

# 3. 清除 env 后补代码，再回归
unset BAA_PDF_FONT
python -m pytest src/tests/test_pdf_report.py src/tests/test_p119_correction_notice.py -q
```

**修复建议**（`components.py` 候选列表追加，Windows 候选之后）——**已实施（2026-10-15）**：

```python
# macOS 系统中文字体（苹方 / 冬青黑体 / 宋体-简）
"/System/Library/Fonts/PingFang.ttc",
"/System/Library/Fonts/Hiragino Sans GB.ttc",
"/System/Library/Fonts/Supplemental/Songti.ttc",
```

注意：PingFang.ttc 为多权重集合，`subfontIndex=0` 取首个子字体，与现有 WQY 同文件伪粗体行为一致；`Hiragino Sans GB.ttc` 路径含空格，`os.path.exists` 不受影响。

**完成判定**：macOS 默认环境（无 `BAA_PDF_FONT`）下 PDF 相关测试全绿。

### 空白 B：F3 成功路径（`shutil.copy2`）从未实际执行

**先决工程疑点**：需先确认 LibreOffice Draw 是否真的具备 **DWG 导出 filter**。若无，`--convert-to dwg` 必 rc≠0，代码虽正确降级 DXF，但 F3 成功路径在现实中**永远不可达**（防御性修复，无覆盖）。

**验证步骤**（在含 LibreOffice 的机器上执行）：

```bash
# 1. 隔离验证转换能力（不经引擎，最小 DXF）
soffice --headless --convert-to dwg --outdir /tmp/out /tmp/min.dxf
echo "rc=$?"
ls -la /tmp/out/

# 2. rc=0 且产出 .dwg → 分支 A：跑引擎级回归闭环
python -m pytest src/tests/test_reverse_roundtrip.py -q

# 3. rc≠0（大概率报 no export filter for dwg）→ 分支 B：记录 stderr 留档
```

**分支处置**：

- **分支 A（确有 DWG filter）**：F3 成功路径真实可达，引擎级测试通过即闭环。
- **分支 B（无 filter，现实概率较大）**，二选一：
  - **B1 保守**：维持现状（降级 DXF），在本清单 F2 表格注明"LibreOffice 无 DWG 导出 filter"；F3 定性为防御性修复。
  - **B2 进阶（推荐）**：DXF→DWG 换用 **ODA File Converter**（ODA 官方免费工具，DWG/DXF 互转事实标准），CLI 明确：`ODAFileConverter <indir> <outdir> ACAD2018 DWG 0 1`。与现有 LibreCAD（DWG→DXF，见 `parsers/dwg_convert.py`）形成完整互转闭环。

**补充单测**（冒烟覆盖成功路径，无 LibreOffice 环境自动跳过）——**已实施（2026-10-15）**：`test_reverse_roundtrip.py::TestExportDwg::test_export_dwg_with_libreoffice`，skipif 复用 `_soffice_available()` 三级探测口径；断言契约"非空 .dwg 或 .dxf 降级"。**在含 LibreOffice 的机器上运行该测试即可落定分支 A/B**（产出 .dwg → 分支 A；降级 .dxf → 分支 B1 现场证据）。

**完成判定**：分支 A/B 落定，F2 表格"待验证"行状态更新，不再有"从未执行"路径。

### 空白 C：soffice 安装路径探测增强

**修复建议**（`reverse_engine.py` `_export_via_libreoffice` 探测段替换）：

```python
soffice = None
# 环境变量显式指定优先
env_path = os.environ.get("BAA_SOFFICE_PATH")
if env_path and os.path.exists(env_path):
    soffice = env_path
if not soffice:
    exe_candidates = ["soffice", "libreoffice"]  # shutil.which 查 PATH
    if os.name == "nt":  # Windows: 补常见安装路径（PATH 外）
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        exe_candidates += [
            os.path.join(pf, "LibreOffice", "program", "soffice.exe"),
            os.path.join(pf86, "LibreOffice", "program", "soffice.exe"),
        ]
    for cand in exe_candidates:
        found = cand if os.path.isabs(cand) else shutil.which(cand)
        if found and os.path.exists(found):
            soffice = found
            break
```

注意：`shutil.which` 返回绝对路径，后续 `cmd = [soffice, ...]` 无需改动。

**验证步骤**（Windows + 默认安装 LibreOffice）：

```powershell
# 1. 安装（或确认已有默认路径安装）
winget install TheDocumentFoundation.LibreOffice

# 2. 确认默认路径存在且 soffice 不在 PATH
Test-Path "C:\Program Files\LibreOffice\program\soffice.exe"
D:\APPstore\miniconda3\python.exe -c "import shutil; print(shutil.which('soffice'))"
#    预期: True / None（证明 PATH 外，改前探测不到）

# 3. 引擎级回归
D:\APPstore\miniconda3\python.exe -m pytest src/tests/test_reverse_roundtrip.py -q
#    修复前: 降级 DXF（测试仍过但走不到转换）；修复后: 探测命中，
#    后续结果取决于空白 B 的分支 A/B
```

**完成判定**：未安装 LibreOffice 时 17 passed 不变（降级路径不受影响）；默认安装后探测命中（日志出现 P67 探测记录）。

## 遗留行动项（汇总）

1. [ ] Linux CI 补跑全量回归，确认 F1 候选列表前 5 项与 F2 语义无漂移。**验证脚本已就绪（2026-10-15）：`python scripts/linux_ci_regression.py`**（阶段 0-5：环境自检 / F1 静态漂移断言 / F1 字体运行时 / F2 探测语义 / 全量回归 / real_drawing 基线；`--probes-only` 快速自检；Windows 本机试运行 8/8 PASS，退出码语义 0=通过 1=漂移）。
2. [ ] **空白 A**：macOS 候选已实施（2026-10-15）；待 macOS 实机回归（步骤 1 复现 → 步骤 3 清 env 验证）。
3. [ ] **空白 B**：冒烟测试已实施（2026-10-15）；待含 LibreOffice 的机器运行 `test_export_dwg_with_libreoffice` 落定分支 A/B（分支 B 建议采纳 B2 ODA File Converter）。
4. [x] **空白 C**：路径探测增强已实施（2026-10-15，`reverse_engine.py`），并配套 6 个单测（`TestSofficeDetection`：env 优先 / env 无效回退 / PATH 采用 / Windows 默认路径 / posix 门控 / 全未命中降级）；全量回归 2246 passed。待有 LibreOffice 环境终验（与空白 B 同机）。
