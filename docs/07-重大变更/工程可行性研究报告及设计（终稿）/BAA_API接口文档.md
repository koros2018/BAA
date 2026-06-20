# BAA API 接口文档

> **版本：** v1.0 | **更新时间：** 2026-06-20  
> **Base URL：** `http://<host>:8000`  
> **认证方式：** Bearer Token（API Key）  
> **内容类型：** `multipart/form-data`（文件上传）/ `application/json`（JSON请求）

---

## 目录

1. [认证方式](#1-认证方式)
2. [端点概览](#2-端点概览)
3. [/health 健康检查](#3-health-健康检查)
4. [/deconstruct 图纸解构](#4-deconstruct-图纸解构)
5. [/review 图纸合规审查](#5-review-图纸合规审查)
6. [/reconstruct BIM重构（付费）](#6-reconstruct-bim重构付费)
7. [/order/{id} 订单查询](#7-orderid-订单查询)
8. [错误码](#8-错误码)
9. [调用示例](#9-调用示例)

---

## 1. 认证方式

### 1.1 API Key 认证

所有受保护端点需要 Bearer Token：

```bash
Authorization: Bearer <your-api-key>
```

### 1.2 获取 API Key

联系 BAA 服务提供方获取 API Key。每个 Key 可设置独立的速率限制和权限范围。

### 1.3 授权令牌（用于付费服务）

`/reconstruct` 等付费端点需要额外的 `auth_token`（JWT格式，HMAC-SHA256签名）：

```json
{
  "auth_token": "eyJhbGciOi...<完整JWT令牌>"
}
```

授权令牌由授权代收代付点生成，包含订单ID、服务类型、有效期、配额等信息。

---

## 2. 端点概览

| 端点 | 方法 | 认证 | 付费 | 说明 |
|------|:----:|:----:|:----:|------|
| `/health` | GET | 否 | 免费 | 服务健康检查 |
| `/deconstruct` | POST | 是 | 免费 | 上传图纸，解析并提取图元信息 |
| `/review` | POST | 是 | 免费 | 上传图纸，执行完整合规审查 |
| `/reconstruct` | POST | 是 | 付费 | BIM重构，需auth_token |
| `/order/{id}` | GET | 是 | — | 查询BIM重构订单状态 |

---

## 3. /health 健康检查

### 请求

```http
GET /health
```

### 响应

```json
{
  "status": "ok",
  "version": "1.0.0",
  "uptime_seconds": 0,
  "engine_status": "ready",
  "supported_formats": ["dxf", "dwg"],
  "api_version": "v1"
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `status` | 服务状态（ok/error） |
| `version` | API版本号 |
| `engine_status` | 引擎状态（ready/loading/error） |
| `supported_formats` | 支持的文件格式列表 |

---

## 4. /deconstruct 图纸解构

上传图纸文件，解析并返回图元分解信息。

### 请求

```http
POST /deconstruct
Authorization: Bearer <api-key>
Content-Type: multipart/form-data

file=<图纸文件>
```

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|:----:|:----:|------|
| `file` | File | 是 | DXF图纸文件（最大50MB） |

### 响应

```json
{
  "status": "success",
  "elements": [
    {"type": "wall", "count": 305, "total_length_m": 45.6},
    {"type": "corridor", "count": 591},
    {"type": "text", "count": 46},
    {"type": "column", "count": 19},
    {"type": "stair", "count": 1}
  ],
  "relations": 462241,
  "findings": 7812,
  "total_checks": 9620,
  "confidence": 0.85,
  "file_id": "baa-file-a1b2c3d4e5f6",
  "processing_time_ms": 2500
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `elements` | 图元分类统计（type+count） |
| `relations` | 空间关系数量 |
| `findings` | 违规判定数量 |
| `total_checks` | 总检查次数（实体数×原子函数数） |
| `confidence` | 整体置信度（0~1） |
| `file_id` | 文件标识（用于后续操作） |
| `processing_time_ms` | 处理耗时（毫秒） |

---

## 5. /review 图纸合规审查

上传图纸，执行完整合规审查，返回违规详情。

### 请求

```http
POST /review
Authorization: Bearer <api-key>
Content-Type: multipart/form-data

file=<图纸文件>
```

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|:----:|:----:|------|
| `file` | File | 是 | DXF图纸文件（最大50MB） |
| `full` | bool | 否 | 是否返回完整图元列表（默认false） |

### 响应

```json
{
  "status": "success",
  "summary": {
    "total_entities": 962,
    "entity_types": {"wall": 305, "corridor": 591, "text": 46, "column": 19, "stair": 1},
    "total_checks": 9620,
    "violations": 7812,
    "violation_by_clause": {
      "GB50016-5.5.18": 4000,
      "GB50016-5.5.17": 1500,
      "GB50016-6.1.1": 1200,
      "GB50016-7.1.1": 800
    }
  },
  "details": [
    {
      "entity_id": "WALL_001",
      "entity_type": "wall",
      "clause_id": "GB50016-5.5.18",
      "clause_title": "疏散楼梯净宽判定",
      "result": "FAIL",
      "extracted_value": 0.0,
      "required_value": 1.2,
      "difference": -1.2,
      "explanation": "WALL_001的value为0.0m，不满足GB50016第5.5.18条要求..."
    }
  ],
  "file_id": "baa-file-a1b2c3d4e5f6",
  "processing_time_ms": 2500
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `summary.total_entities` | 识别到的实体总数 |
| `summary.entity_types` | 实体类型分布 |
| `summary.total_checks` | 总检查次数 |
| `summary.violations` | 违规总数 |
| `summary.violation_by_clause` | 按条款汇总的违规数 |
| `details[].entity_id` | 违规实体ID |
| `details[].clause_id` | 违反的规范条款 |
| `details[].extracted_value` | 提取到的实际值 |
| `details[].required_value` | 规范要求值 |
| `details[].difference` | 差值（负数=不足） |
| `details[].explanation` | 违规说明 |

---

## 6. /reconstruct BIM重构（付费）

根据图纸自动生成BIM模型（IFC格式）。需要授权令牌。

### 请求

```http
POST /reconstruct
Authorization: Bearer <api-key>
Content-Type: application/json

{
  "file_id": "baa-file-a1b2c3d4e5f6",
  "auth_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "order_id": "ema2-order-001"
}
```

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|:----:|:----:|------|
| `file_id` | string | 是 | 来自/deconstruct或/review的file_id |
| `auth_token` | string | 是 | 授权代收代付点生成的JWT令牌 |
| `order_id` | string | 是 | EMA2侧的订单ID |

### 响应

```json
{
  "status": "success",
  "order_id": "ema2-order-001",
  "baa_order_id": "baa-order-a1b2c3d4",
  "model_url": "http://localhost:8000/models/baa-order-a1b2c3d4/model.ifc",
  "elements_count": 40,
  "processing_time_ms": 15000,
  "file_size_mb": 2.5,
  "valid_until": "2026-07-20T12:00:00Z"
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `order_id` | EMA2侧订单ID（回传） |
| `baa_order_id` | BAA侧内部订单ID |
| `model_url` | 生成的IFC模型下载地址 |
| `elements_count` | BIM模型包含的构件数 |
| `valid_until` | 模型下载链接有效期 |

### 授权令牌生成规范

auth_token为JWT格式，由授权代收代付点生成：

```python
import hmac, hashlib, base64, json

payload = {
    "order_id": "ema2-order-001",
    "service": "reconstruct",
    "issued_at": "2026-06-20T09:00:00",
    "expires_at": "2026-06-20T12:00:00",
    "quota": {"max_requests": 1, "max_file_size_mb": 50},
    "client_id": "ema2-platform"
}

header = {"alg": "HS256", "typ": "JWT"}
header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
signing_input = f"{header_b64}.{payload_b64}"

# 使用共享密钥签名
sig = hmac.new(SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
token = f"{header_b64}.{payload_b64}.{sig_b64}"
```

---

## 7. /order/{id} 订单查询

查询BIM重构订单状态和模型下载地址。

### 请求

```http
GET /order/{order_id}
Authorization: Bearer <api-key>
```

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|:----:|:----:|------|
| `order_id` | string (path) | 是 | BAA侧订单ID（来自/reconstruct响应） |

### 响应（已完成）

```json
{
  "status": "completed",
  "order_id": "baa-order-a1b2c3d4",
  "progress": 100,
  "model_url": "/models/baa-order-a1b2c3d4/model.ifc",
  "file_size_mb": 2.5
}
```

### 响应（处理中）

```json
{
  "status": "processing",
  "order_id": "baa-order-a1b2c3d4",
  "progress": 50,
  "estimated_remaining_ms": 15000
}
```

---

## 8. 错误码

| HTTP状态码 | error_code | 说明 |
|:----------:|------------|------|
| 400 | `UNSUPPORTED_FORMAT` | 不支持的文件格式（仅支持dxf/dwg） |
| 400 | `FILE_TOO_LARGE` | 文件超过50MB限制 |
| 401 | `INVALID_API_KEY` | API Key无效或未提供 |
| 402 | `AUTH_FAILED` | 授权令牌验证失败（过期/签名无效） |
| 404 | `FILE_NOT_FOUND` | file_id对应的文件不存在 |
| 404 | `ORDER_NOT_FOUND` | 订单ID不存在 |
| 500 | `PARSE_FAILED` | 图纸解析失败（文件损坏/格式不兼容） |

### 错误响应格式

```json
{
  "status": "error",
  "error_code": "UNSUPPORTED_FORMAT",
  "message": "不支持的文件格式: pdf。支持: dxf, dwg"
}
```

---

## 9. 调用示例

### cURL

```bash
# 健康检查
curl http://localhost:8000/health

# 图纸解析
curl -X POST http://localhost:8000/deconstruct \
  -H "Authorization: Bearer your-api-key" \
  -F "file=@drawing.dxf"

# 图纸合规审查
curl -X POST http://localhost:8000/review \
  -H "Authorization: Bearer your-api-key" \
  -F "file=@drawing.dxf"

# BIM重构
curl -X POST http://localhost:8000/reconstruct \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "baa-file-a1b2c3d4e5f6",
    "auth_token": "eyJhbGciOi...",
    "order_id": "ema2-order-001"
  }'

# 订单查询
curl http://localhost:8000/order/baa-order-a1b2c3d4 \
  -H "Authorization: Bearer your-api-key"
```

### Python

```python
import requests

API_BASE = "http://localhost:8000"
API_KEY = "your-api-key"

# 上传并审查
with open("drawing.dxf", "rb") as f:
    resp = requests.post(
        f"{API_BASE}/review",
        files={"file": ("drawing.dxf", f, "application/dxf")},
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
data = resp.json()
print(f"实体: {data['summary']['total_entities']}")
print(f"违规: {data['summary']['violations']}")

# BIM重构
resp = requests.post(
    f"{API_BASE}/reconstruct",
    json={
        "file_id": data["file_id"],
        "auth_token": "<JWT token from payment provider>",
        "order_id": "ema2-order-001",
    },
    headers={"Authorization": f"Bearer {API_KEY}"},
)
print(f"BIM模型: {resp.json()['model_url']}")
```

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|:----:|:----:|---------|
| v1.0 | 2026-06-20 | 初始版本，覆盖全部5个端点 |
