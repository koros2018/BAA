# BAA Code Wiki

> **BAA（Blueprint AI Agent / 蓝图智能体）** —— 面向建筑图纸的智能合规审查系统。
> 将 DWG / DXF / PDF 图纸解析为结构化实体，通过语义分析与「原子函数」规范判定引擎，
> 输出可追溯的合规审查结论、PDF 报告、修正建议与协作审核流。

本 Wiki 面向开发者，描述项目的整体架构、模块职责、关键类与函数、依赖关系与运行方式。

## 文档索引

| 分册 | 内容 |
| --- | --- |
| [01-architecture.md](./01-architecture.md) | 整体架构、分层设计、端到端数据流、关键设计决策 |
| [02-modules.md](./02-modules.md) | 目录结构与各模块职责（引擎 / API / 前端 / SDK / MCP / Skill） |
| [03-core-engine.md](./03-core-engine.md) | 核心类与函数说明（Parser / SemanticAnalyzer / FuncRegistry / SpecRepository / ReviewQueue / Report / Correction 等），含语义图层规则（Layer Rules）分片详解 |
| [04-api-reference.md](./04-api-reference.md) | REST API 端点总览与鉴权模型 |
| [05-dependencies.md](./05-dependencies.md) | 依赖清单与模块间依赖关系 |
| [06-run-and-deploy.md](./06-run-and-deploy.md) | 本地运行、测试、Docker / K8s 部署与 CI |

## 项目速览

| 项 | 值 |
| --- | --- |
| 项目名 | BAA（Blueprint AI Agent） |
| 语言 / 运行时 | Python 3.12；前端 TypeScript + Vite |
| 当前版本 | `v2.5.79-stable`（API 版本号 `1.25.0`） |
| 后端框架 | FastAPI + Uvicorn / Gunicorn |
| 图纸内核 | ezdxf、ezdwg、PyMuPDF (fitz)、reportlab |
| 规范知识库 | 199 条 `Clause`（GB50016 / GB50974 / GB50763 / GB50067 / NFPA101 / NFPA5000） |
| 原子函数 | 431 条 `AtomicFunction`（DIM / DIST / EXIST / COUNT / AREA / ATTR / EVAC / ACCESS / LIGHT / THERMAL / STRUCTURAL） |
| 对外接入 | REST API、Python SDK、MCP Server、Skill 包 |
| 测试规模 | 2224 passed / 3 skipped / 0 failed（`VERSION.md`） |

## 核心能力地图

```
图纸导入 ──► 解析管线 ──► 语义识别 ──► 原子函数判定 ──► 报告/修正/反馈
   │            │             │              │
 DX/DWG/PDF   矢量原生    图层规则+扫线    431 条原子函数
             六级兜底    房间/关系/疏散    199 条规范条款
```

## 快速上手

```bash
# 安装依赖
pip install -r requirements.txt

# 启动开发服务
uvicorn src.api.baa_api:app --reload --port 8000

# 运行测试（默认排除 slow / real_drawing）
pytest

# 调用核心审查接口
curl -X POST "http://localhost:8000/review?standard=GB%2050016-2014" \
     -F "file=@drawing.dxf"
```

详见 [06-run-and-deploy.md](./06-run-and-deploy.md)。
