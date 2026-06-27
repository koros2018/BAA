# BAA API 使用说明 — EMA2 第三方对接

> 版本: v1.23.0 | 更新日期: 2026-06-27

---

## 1. API 概述

BAA（Building Audit Assistant）提供 RESTful API，供 EMA2 等第三方系统调用，实现建筑图纸的自动化规范审查。

**核心能力：**
- 异步图纸审查（支持 DXF 格式）
- 任务状态轮询
- Webhook 回调通知
- 完整违规归因报告

**基础 URL:** `http://<your-baa-host>:8000`

---

## 2. 认证方式

所有 API 请求需携带 API Key：

```
Header: x-api-key: <your-api-key>
```

API Key 由 BAA 管理员通过 `/admin/keys` 接口创建。

---

## 3. 端点说明

### 3.1 创建异步审查任务

**POST** `/api/v1/tasks`

上传图纸文件，创建异步审查任务。任务完成后通过轮询或 Webhook 获取结果。

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | ✅ | 图纸文件（DXF 格式） |
| building_type | Query | ❌ | 建筑类型：`civil`（民用）或 `industrial`（工业），默认 `civil` |
| webhook_url | Query | ❌ | 回调通知 URL（可选） |

**请求示例：**

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -F "file=@/path/to/drawing.dxf" \
  -H "x-api-key: ***"
```

**响应示例：**

```json
{
  "status": "success",
  "task_id": "9b9a2084",
  "status_url": "/api/v1/tasks/9b9a2084",
  "result_url": "/api/v1/tasks/9b9a2084/result"
}
```

---

### 3.2 查询任务状态

**GET** `/api/v1/tasks/{task_id}`

查询审查任务的当前状态。

**请求示例：**

```bash
curl http://localhost:8000/api/v1/tasks/9b9a2084 \
  -H "x-api-key: ***"
```

**响应示例：**

```json
{
  "status": "success",
  "task_id": "9b9a2084",
  "state": "completed",
  "filename": "E-00-11-01电力配电箱系统图.dxf",
  "created_at": "2026-06-27T14:40:30.208407",
  "updated_at": "2026-06-27T14:40:30.563258",
  "error": null
}
```

**状态值说明：**

| state | 含义 |
|-------|------|
| pending | 任务排队中 |
| running | 任务执行中 |
| completed | 任务完成 |
| failed | 任务失败 |

---

### 3.3 获取审查结果

**GET** `/api/v1/tasks/{task_id}/result`

获取审查任务的完整结果。任务必须处于 `completed` 状态。

**请求示例：**

```bash
curl http://localhost:8000/api/v1/tasks/9b9a2084/result \
  -H "x-api-key: ***"
```

**响应示例：**

```json
{
  "status": "success",
  "task_id": "9b9a2084",
  "result": {
    "summary": {
      "total_entities": 311,
      "violations": 22,
      "entity_types": {
        "text": 2,
        "dimension": 186,
        "wall": 56,
        "door": 37,
        "corridor": 14,
        "column": 16
      }
    },
    "details": [
      {
        "entity_id": "door_001",
        "entity_type": "door",
        "clause_id": "GB50016-5.5.19",
        "clause_title": "疏散门净宽判定",
        "result": "FAIL",
        "extracted_value": 0.85,
        "required_value": 0.9,
        "difference": -0.05,
        "explanation": "疏散门净宽 0.85m，低于规范要求的 0.9m",
        "severity": "major"
      }
    ],
    "processing_time_ms": 360
  }
}
```

---

### 3.4 注册 Webhook 回调

**POST** `/api/v1/webhooks`

注册 Webhook，任务完成后自动推送通知。

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| url | Query | ✅ | 回调 URL |
| events | Query | ❌ | 触发事件：`completed`、`failed`、`all`，默认 `completed` |

**请求示例：**

```bash
curl -X POST "http://localhost:8000/api/v1/webhooks?url=http://ema2.example.com/callback&events=completed" \
  -H "x-api-key: ***"
```

**响应示例：**

```json
{
  "status": "success",
  "webhook_id": "3a89764c",
  "url": "http://ema2.example.com/callback",
  "events": "completed"
}
```

**Webhook 回调 payload：**

```json
{
  "task_id": "9b9a2084",
  "status": "completed",
  "violations": 22,
  "entities": 311,
  "processing_time_ms": 360
}
```

---

### 3.5 查询 Webhook 列表

**GET** `/api/v1/webhooks`

**请求示例：**

```bash
curl http://localhost:8000/api/v1/webhooks \
  -H "x-api-key: ***"
```

**响应示例：**

```json
{
  "status": "success",
  "webhooks": [
    {
      "webhook_id": "3a89764c",
      "url": "http://ema2.example.com/callback",
      "events": "completed",
      "active": true,
      "created_at": "2026-06-27T14:45:00.000000"
    }
  ]
}
```

---

### 3.6 删除 Webhook

**DELETE** `/api/v1/webhooks/{webhook_id}`

**请求示例：**

```bash
curl -X DELETE http://localhost:8000/api/v1/webhooks/3a89764c \
  -H "x-api-key: ***"
```

**响应示例：**

```json
{
  "status": "success",
  "message": "Webhook 已删除"
}
```

---

## 4. 错误码

| HTTP 状态码 | 错误码 | 说明 |
|-------------|--------|------|
| 400 | UNSUPPORTED_FORMAT | 文件格式不支持 |
| 400 | FILE_TOO_LARGE | 文件超过 50MB 限制 |
| 401 | INVALID_API_KEY | API Key 无效 |
| 404 | TASK_NOT_FOUND | 任务不存在 |
| 404 | WEBHOOK_NOT_FOUND | Webhook 不存在 |
| 409 | - | 任务仍在处理中 |
| 500 | TASK_FAILED | 任务执行失败 |

---

## 5. 使用流程

### 方式一：轮询模式

```
1. POST /api/v1/tasks → 获取 task_id
2. 循环 GET /api/v1/tasks/{task_id} → 直到 state=completed
3. GET /api/v1/tasks/{task_id}/result → 获取审查结果
```

### 方式二：Webhook 模式

```
1. POST /api/v1/webhooks → 注册回调 URL
2. POST /api/v1/tasks?webhook_url=<url> → 创建任务
3. 等待 Webhook 回调通知
4. GET /api/v1/tasks/{task_id}/result → 获取审查结果
```

---

## 6. 注意事项

1. **文件格式**：仅支持 DXF 格式
2. **文件大小**：最大 50MB
3. **任务存储**：当前为内存存储，服务重启后任务数据丢失
4. **Webhook 超时**：回调请求超时 10 秒，失败不重试
5. **API Key 安全**：请勿在客户端代码中硬编码 API Key

---

## 7. 联系支持

如有问题，请联系 BAA 管理员获取 API Key 或技术支持。
