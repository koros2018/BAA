# BAA Python SDK

建筑图纸 AI 合规审查系统的轻量 Python 客户端。

## 安装

```bash
pip install baa-sdk
```

或从源码安装（monorepo 内）：

```bash
cd src/sdk
pip install -e .
```

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

## 许可证

MIT
