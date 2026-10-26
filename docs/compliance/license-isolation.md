# 第三方组件许可合规说明（T-C4）

日期：2026-10-25　范围：BAA 服务运行依赖（`requirements.txt` 全量）

## 1. 许可扫描结论

扫描工具：`pip-licenses`（运行环境全量包）。GPL 家族组件清单：

| 组件 | 版本 | 许可 | 用途 | 合规处置 |
|---|---|---|---|---|
| PyMuPDF | 1.27.2.2 | **AGPL-3.0** 或 Artifex 商业许可（双许可） | PDF→DXF 矢量提取 | **独立进程隔离**（见 §2） |
| psycopg / psycopg-binary | 3.3.6 | LGPL-3.0-only | PostgreSQL 驱动 | 动态链接 + 未修改源码，符合 LGPL（见 §3） |
| psycopg2-binary | 2.9.12 | LGPL | PostgreSQL 驱动（alembic 兼容） | 同上 |
| frozendict | 2.4.6 | LGPLv3 | 不可变字典（间接依赖） | 同上 |
| ifcopenshell | 0.9.0.post1 | LGPL-3.0 | IFC4 输出（T-C8 `ifc_export.py`） | 同上（动态 import，未修改源码） |
| casadi | 3.7.x | LGPL-3.0 | cadquery 传递依赖（T-C8 STEP 输出） | 同上 |

其余依赖均为 MIT / BSD / Apache-2.0 等宽松许可，无特殊义务。

## 2. PyMuPDF（AGPL）进程隔离方案

AGPL-3.0 的核心义务：通过网络向用户提供服务的"修改版或基于 AGPL 组件的程序"
需以 AGPL 开源。BAA 为商业闭源产品，采用**进程边界隔离**使主程序不形成
"基于 AGPL 组件的单一程序"：

```
┌─────────────────────────────┐      CLI 参数 + stdout JSON      ┌──────────────────────────┐
│  BAA 主服务进程（闭源）        │  ─────────────────────────────▶ │  pdf_service 独立进程      │
│  FastAPI / 审查管线           │  python -m parsers.pdf_service  │  （唯一 import PyMuPDF）   │
│  不 import pymupdf/fitz      │  ◀─────────────────────────────  │  pdf_parser.pdf_to_dxf    │
└─────────────────────────────┘      {"ok": true, "result": …}   └──────────────────────────┘
```

技术实现：

- 唯一 PyMuPDF 引用点：[pdf_parser.py](../../src/baa_engine/parsers/pdf_parser.py)（`import pymupdf as fitz`）。
- 唯一进程入口：[pdf_service.py](../../src/baa_engine/parsers/pdf_service.py)（`python -m src.baa_engine.parsers.pdf_service`）。
- 主进程侧封装：[pdf_isolation.py](../../src/baa_engine/parsers/pdf_isolation.py)（**不含** PyMuPDF 导入，
  仅 subprocess + JSON 通信）。
- 主链路调用点：[drawing_parser.py](../../src/baa_engine/drawing_parser.py) `.pdf` 分支，
  默认 `BAA_PDF_ISOLATION=1` 走子进程；`=0` 仅用于本地开发/测试的回退。
- 两进程无共享内存/动态链接/插件式调用，仅命令行参数与 stdout JSON——
  符合 FSF 对"aggregate（聚合体）"的界定（两个独立程序经管道/命令行通信
  不构成单一衍生作品）。
- 测试与工具脚本（`src/tests/test_pdf_pipeline.py`）在测试进程内直接调用
  pdf_parser，属内部研发活动，不向第三方提供网络服务，不触发 AGPL §13。

注意：本隔离基于"独立程序聚合"解释，属业界通行做法（与 MongoDB SSPL 前
驱动隔离、Ghostscript AGPL 命令行调用模式一致）。若法务要求更强保证，
可采购 Artifex 商业许可替换 AGPL 路径（接口不变，仅需在 pdf_service 中
使用商业版 PyMuPDF）。

## 3. LGPL 组件（psycopg / psycopg2 / frozendict / ifcopenshell / casadi）

- 使用方式：Python 动态导入（相当于动态链接），**未修改任何上游源码**。
- LGPL-3.0 §4 义务：允许用户替换库版本（pip 安装即满足）、提供许可文本
  与版权声明。已在 `requirements.txt` 注明版本来源，许可文本随上游包分发。
- 无 copyleft 传导至 BAA 主代码。

## 4. 持续合规机制

- `src/tests/test_security_tc4.py`（TestLicenseIsolation）：
  - 断言主进程不加载 PyMuPDF（`drawing_parser` 导入后 `sys.modules` 无 pymupdf/fitz）；
  - 断言 AGPL 组件清单不扩大（pip-licenses 全量扫描白名单比对）。
- 新增依赖评审要求：引入 GPL/AGPL/SSPL 组件必须走独立进程或替换方案，
  并更新本文档表格。
