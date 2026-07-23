# P64: OpenAPI 自动生成 + SDK

## 概述

BAA 后端基于 FastAPI，自动生成标准 OpenAPI 3.0 规范文档（63 个 API 路径）。P64 增强：

1. **OpenAPI 元信息增强** — 版本、描述、标签分类
2. **轻量 Python SDK** — `src/sdk/__init__.py`，无外部依赖，httpx 可选
3. **交互式文档** — `/docs`（Swagger UI）+ `/redoc`（Redoc）

## OpenAPI 文档地址

- **Swagger UI**: `http://<host>:8000/docs`
- **Redoc**: `http://<host>:8000/redoc`
- **JSON**: `http://<host>:8000/openapi.json`

### 标签分类

| 标签 | 说明 |
|------|------|
| System | 健康检查、根路径 |
| Deconstruct | 图纸解构 |
| Review | 合规审查、热工、重建 |
| API | API v1 原子函数/规范管理 |
| Admin | API 密钥管理、EMA2、Feedback |
| Collaboration | 团队协作（P43） |
| Render | 图纸渲染 |

## Python SDK 使用

```bash
# 安装（可选，有 httpx 更快）
pip install httpx

# 无 httpx 时自动降级标准库 urllib
```

```python
from src.sdk import BAAClient, BAAError

client = BAAClient(
    api_key="***",
    base_url="http://localhost:8000",
)

# 健康检查
health = client.health()
print(health["version"])  # "1.25.0"

# 审查图纸（核心）
result = client.review(
    "drawing.dxf",
    standard="GB 50016-2014",
    building_type="civil",
)
# 查看 TOP-5 违规
for v in result["structured_summary"]["top_violations"]:
    print(f"{v['priority']} {v['func_id']} {v['clause_title']}")

# 从结构化数据审查（跳过图纸解析）
result = client.review_from_data(
    entities=[{"type": "wall", "id": "W1", ...}],
    standard="GB 50016-2014",
)

# 图纸解构
data = client.deconstruct("drawing.dxf")

# 批量审查
batch = client.batch_review(["a.dxf", "b.dxf"])

# 审查历史
history = client.review_history(limit=10)

# 热工 K 值反算
k = client.thermal_k_value({"thickness": 0.12, "material": "concrete"})

# 原子函数列表
funcs = client.list_functions()

# 反向重构
dxf = client.reverse_generate({"rooms": [...]})
```

### 异常处理

```python
try:
    result = client.review("bad-file.dxf")
except BAAError as e:
    print(f"API 错误: {e}")
```

### 核心方法清单

| 方法 | 端点 | 说明 |
|------|------|------|
| `health()` | `GET /health` | 健康检查 |
| `review()` | `POST /review` | 图纸审查 |
| `review_from_data()` | `POST /review-from-data` | 结构化数据审查 |
| `deconstruct()` | `POST /deconstruct` | 图纸解构 |
| `batch_review()` | `POST /batch-review` | 批量审查 |
| `reconstruct()` | `POST /reconstruct` | 数据重建 |
| `list_functions()` | `GET /api/v1/functions` | 原子函数列表 |
| `list_specs()` | `GET /api/v1/specs` | 规范标准列表 |
| `update_function()` | `POST /api/v1/functions/{id}/update` | 更新函数参数 |
| `reverse_generate()` | `POST /api/v1/reverse` | 单房间 DXF 生成 |
| `reverse_generate_multi()` | `POST /api/v1/reverse/multi` | 多房间 DXF 生成 |
| `correction_suggestions()` | `POST /api/v1/correction/suggestions` | 修正建议 |
| `review_history()` | `GET /review/history` | 审查历史 |
| `review_detail()` | `GET /review/history/{id}` | 审查详情 |
| `clear_review_history()` | `DELETE /review/history` | 清空历史 |
| `review_project_summary()` | `GET /review/project/summary` | 项目汇总 |
| `thermal_k_value()` | `POST /thermal/k-value` | 热工 K 值反算 |
| `render_drawing()` | `GET /render/{id}` | 渲染图纸 |
| `create_ema2_task()` | `POST /api/v1/tasks` | EMA2 任务创建 |
| `ema2_task_status()` | `GET /api/v1/tasks/{id}` | EMA2 任务状态 |
| `ema2_task_result()` | `GET /api/v1/tasks/{id}/result` | EMA2 任务结果 |

## 验证

```bash
cd Projects/BAA
python3 -c "
from src.sdk import BAAClient
c = BAAClient(api_key='***', base_url='http://127.0.0.1:8000')
assert c.health()['status'] == 'ok'
result = c.review('data/files/baa-file-00877f184d81.dxf')
assert result['status'] == 'success'
assert 'structured_summary' in result
print('✅ SDK 验证通过')
"
```
