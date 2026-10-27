# BAA Python SDK

建筑图纸 AI 合规审查系统的轻量 Python 客户端。

## 安装

```bash
pip install baa-sdk
```

或从源码安装（monorepo 内）：

```bash
pip install ./src/sdk
```

## 10 分钟跑通

无需启动服务即可先跑离线示例（自动导出知识库包）：

```bash
python src/sdk/examples/quickstart_offline.py
# [OK] 离线示例跑通（全程无需网络与服务）
```

在线示例（先 `docker compose up -d` 或 `uvicorn src.api.baa_api:app --port 8000`）：

```bash
python src/sdk/examples/quickstart_online.py http://localhost:8000 your-api-key
```

## 知识库包（离线）

服务端一键导出（原子函数 + 规范条文 + 版本元数据，含 sha256 校验）：

```bash
python -m src.baa_engine.knowledge -o dist/baa_knowledge.zip
```

SDK 加载并校验（schema 主版本不兼容、校验和不匹配、条目计数不一致均拒绝）：

```python
from baa_sdk import KnowledgeBundle

kb = KnowledgeBundle.load("dist/baa_knowledge_v1.0.0.zip")
print(kb.summary())          # schema_version / kb_version / counts / standards
print(kb.function("DIM-001"))  # 单条原子函数
print(kb.specs_by_standard())  # 按标准分组的规范条文
```

包内文件：`manifest.json` / `functions.json` / `specs.json` / `versions.json`。

## 快速开始

```python
from baa_sdk import BAAClient

client = BAAClient(api_key="your-api-key", base_url="http://localhost:8000")

# 健康检查
client.health()

# 审查图纸
result = client.review("/path/to/drawing.dxf")
print(result["structured_summary"]["top_violations"])

# 多 Sheet 审查
multi = client.review_multi_sheet("/path/to/drawing.dxf")

# 统计仪表盘
stats = client.stats()

# 批量审查
client.batch_review(["a.dxf", "b.dxf"])
```

## 端点覆盖

| 方法 | API 端点 |
|------|----------|
| `health()` | `GET /health` |
| `review()` | `POST /review` |
| `review_from_data()` | `POST /review-from-data` |
| `deconstruct()` | `POST /deconstruct` |
| `batch_review()` | `POST /batch-review` |
| `review_multi_sheet()` | `POST /api/v1/review-multi-sheet` |
| `reverse_generate()` | `POST /api/v1/reverse` |
| `reverse_generate_multi()` | `POST /api/v1/reverse/multi` |
| `stats()` | `GET /api/v1/stats` |
| `register_webhook()` | `POST /api/v1/admin/webhooks/register` |
| `list_feedbacks()` | `GET /api/v1/feedbacks` |
| `list_construction_review_items()` | `GET /api/v1/construction-review` |
| `construction_review_report()` | `POST /api/v1/construction-review/report` |
| `list_functions()` | `GET /api/v1/functions` |
| `list_specs()` | `GET /api/v1/specs` |
| `spec_versions()` | `GET /api/v1/specs/versions` |

## 许可证

MIT

---

## 交付物版本兼容矩阵（D3-T4）

| SDK 版本 | report_schema_version | kb_schema_version | 发布说明 |
|----------|----------------------|-------------------|---------|
| >= 2.5.80 | 1.x | 1.x | 新增 ReportBundle + VersionMismatchError |
| 待定 2.6.0 | 1.x, 2.x | 1.x, 2.x | 支持 schema v2 交付物包 |

**使用示例**：
```python
from baa_sdk import ReportBundle, VersionMismatchError

try:
    rb = ReportBundle.load("exports/review_xxx.zip")
    print(rb.summary())
except VersionMismatchError as e:
    print(f"版本不兼容，请升级 SDK: {e}")
```
