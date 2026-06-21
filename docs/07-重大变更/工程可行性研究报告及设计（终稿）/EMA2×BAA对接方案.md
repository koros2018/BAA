# EMA2 × BAA 对接方案

> **版本：** v1.0 | **更新时间：** 2026-06-21  
> **适用对象：** EMA2团队、BAA开发团队  
> **文档位置：** `docs/07-重大变更/工程可行性研究报告及设计（终稿）/EMA2×BAA对接方案.md`

---

## 1. 对接概述

### 1.1 背景

EMA2 项目为 BAA 项目提供"代收代付"服务。用户通过 EMA2 使用 BAA 的图纸审查和 BIM 重构能力，EMA2 负责前端展示、收款和任务编排，BAA 负责核心图纸引擎。

### 1.2 角色边界

| 角色 | 负责 | 不负责 |
|------|------|--------|
| **EMA2** | 前端UI、收款、任务编排、通知用户 | 图纸解析、规范判定、BIM生成 |
| **BAA** | 图纸解构、合规审查、BIM重构 | 定价、收款、用户管理 |
| **授权代收代付点** | 处理支付、生成auth_token | — |

### 1.3 核心原则

- BAA **不处理定价和收款**，仅验证授权代收代付点传输的支付信息
- 免费服务（deconstruct/review）**无需支付**，直接调用
- 付费服务（reconstruct）需 **auth_token** 验证后执行
- 所有异常必须有明确的 error_code 和 message

### 1.4 总流程

```
用户 → EMA2前端 → [上传图纸] → BAA审查（免费） → 展示结果
                                    ↓ 用户确认付费
                               EMA2引导支付 → 代收代付点收款
                                    ↓
                               生成auth_token → EMA2调BAA重构
                                    ↓
                               BAA验证 → 重构 → 回传 → EMA2展示
                                    ↓
                                 用户下载模型
```

---

## 2. API 对接清单

### 2.1 BAA 端点一览

| 端点 | 方法 | 用途 | 认证 | 是否收费 | 超时建议 |
|------|:----:|------|:----:|:--------:|:--------:|
| `GET /health` | — | 健康检查 | 无 | ❌ | 10s |
| `POST /deconstruct` | multipart | 图纸解构 | API Key | ❌ 免费 | 60s |
| `POST /review` | multipart | 合规审查 | API Key | ❌ 免费 | 60s |
| `POST /reconstruct` | JSON | BIM重构 | API Key + auth_token | ✅ 付费 | 120s |
| `GET /order/{order_id}` | — | 查询任务状态 | API Key | ❌ | 10s |

### 2.2 端点详情

#### GET /health

```json
// 请求：无参数
// 成功响应 200
{
  "status": "ok",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "engine_status": "ready",
  "supported_formats": ["dxf", "dwg"]
}
```

#### POST /deconstruct

```
// 请求：multipart/form-data
// 参数：
//   file: 图纸文件（支持 dxf/dwg，最大50MB）
//   building_type: "civil"（民用）| "industrial"（工业），默认"civil"
// Header: Authorization: Bearer <api_key>

// 成功响应 200
{
  "status": "success",
  "elements": [
    {"type": "wall", "count": 7, "total_length_m": 24.5},
    {"type": "door", "count": 2, "total_count": 2},
    {"type": "stair", "count": 1, "total_length_m": 0.0}
  ],
  "entity_count": 12,
  "relations": 80,
  "confidence": 0.85,
  "file_id": "baa-file-xxx",
  "building_type": "civil",
  "processing_time_ms": 2550
}

// 异常响应
// 400: 文件格式不支持 / 文件过大
{"status": "error", "error_code": "UNSUPPORTED_FORMAT", "message": "不支持的文件格式，仅支持 dxf/dwg"}
{"status": "error", "error_code": "FILE_TOO_LARGE", "message": "文件超过50MB限制"}
// 500: 解析失败 / 引擎错误
{"status": "error", "error_code": "PARSE_FAILED", "message": "图纸解析失败"}
{"status": "error", "error_code": "ENGINE_ERROR", "message": "引擎处理异常"}
```

#### POST /review

```
// 请求：multipart/form-data
// 参数：
//   file: 图纸文件
//   building_type: "civil" | "industrial"
//   full: "true" | "false"（是否返回完整图元列表）
// Header: Authorization: Bearer <api_key>

// 成功响应 200
{
  "status": "success",
  "summary": {
    "total_entities": 12,
    "entity_types": {"wall": 7, "door": 2, "stair": 1, "exit": 2},
    "total_checks": 1184,
    "violations": 5,
    "violation_by_clause": {"GB50016-5.5.18": 2, "GB50016-6.1.1": 1, ...}
  },
  "findings": [
    {
      "entity_id": "stair_001",
      "entity_type": "staircase",
      "clause_id": "GB50016-5.5.18",
      "clause_title": "疏散楼梯净宽",
      "result": "FAIL",
      "extracted_value": 1.1,
      "required_value": 1.2,
      "difference": 0.1,
      "explanation": "staircase楼梯净宽1.1m小于1.2m"
    }
  ],
  "file_id": "baa-file-xxx",
  "building_type": "civil",
  "processing_time_ms": 4580
}
```

#### POST /reconstruct

```
// 请求：application/json
// Body：
{
  "file_id": "baa-file-xxx",      // 必填，解构接口返回的file_id
  "auth_token": "eyJhbG...",     // 必填，支付授权令牌
  "order_id": "ema2-order-001",  // 推荐，EMA2侧订单ID
  "options": {                    // 可选，重构参数
    "lod": 200,                   // LOD等级: 100/200/300
    "format": "ifc",             // 输出格式: ifc/obj/fbx
    "include_reinforcement": false
  }
}
// Header: Authorization: Bearer <api_key>

// 成功响应 200
{
  "status": "success",
  "order_id": "baa-order-xxx",
  "model_file": "baa-order-xxx.ifc",
  "lod": 200,
  "format": "ifc",
  "elements_count": 12,
  "auth_info": {
    "client_id": "ema2-platform",
    "service": "reconstruct",
    "expires_at": "2026-06-21T14:00:00"
  }
}

// 异常响应
// 401: auth_token无效 / 过期
{"status": "error", "error_code": "AUTH_FAILED", "message": "支付授权验证失败，请确认订单已支付"}
{"status": "error", "error_code": "TOKEN_EXPIRED", "message": "支付授权已过期，请重新支付"}
// 404: file_id不存在
{"status": "error", "error_code": "FILE_NOT_FOUND", "message": "文件不存在，请重新上传"}
// 500: 重构失败
{"status": "error", "error_code": "RECONSTRUCT_FAILED", "message": "BIM模型生成失败"}
```

#### GET /order/{order_id}

```
// 请求：路径参数 order_id
// Header: Authorization: Bearer <api_key>

// 成功响应 200
{
  "order_id": "baa-order-xxx",
  "status": "completed",          // processing | completed | failed
  "created_at": "2026-06-21T12:00:00",
  "result": {
    "model_file": "baa-order-xxx.ifc",
    "file_size_bytes": 2048000
  }
}
```

---

## 3. 授权令牌规范

### 3.1 令牌格式

auth_token 为 JWT 格式（HMAC-SHA256 签名），由三部分组成：

```
{header}.{payload}.{signature}
```

### 3.2 Payload 字段

| 字段 | 类型 | 必填 | 说明 |
|------|:----:|:----:|------|
| `order_id` | string | 是 | EMA2侧订单ID |
| `service` | string | 是 | 服务类型：`reconstruct` |
| `issued_at` | string (ISO8601) | 是 | 令牌签发时间 |
| `expires_at` | string (ISO8601) | 是 | 令牌过期时间（建议2-3小时） |
| `quota.max_requests` | int | 是 | 最大请求次数（通常为1） |
| `quota.max_file_size_mb` | int | 是 | 文件大小上限 |
| `client_id` | string | 是 | 客户端标识：`ema2-platform` |

### 3.3 令牌示例

```
eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.
eyJvcmRlcl9pZCI6ICJlbWEyLW9yZGVyLTAwMSIsICJzZXJ2aWNlIjogInJlY29uc3RydWN0In0.
x1Y2Z3a4b5c6d7e8f9g0h1i2j3k4l5m6n7o8p9q0r1s2t3u4v5w6x7y8z9
```

### 3.4 安全注意事项

1. 共享密钥 `BAA_AUTH_SECRET` 不得在前端暴露，仅授权代收代付点和 BAA 后端持有
2. 每个 auth_token 仅能使用一次（`max_requests: 1`）
3. 令牌有效期建议 2-3 小时
4. 生产环境必须使用 HTTPS
5. 密钥轮换周期 90 天，旧密钥 48 小时宽限期

---

## 4. 异常处理对照表

| 场景 | error_code | HTTP状态码 | EMA2处理方式 | 用户提示 |
|:----:|-----------|:---------:|-------------|---------|
| 文件格式不支持 | UNSUPPORTED_FORMAT | 400 | 提示用户重传 | "仅支持DXF/DWG格式" |
| 文件过大 | FILE_TOO_LARGE | 400 | 提示压缩 | "文件超过50MB限制" |
| 图纸解析失败 | PARSE_FAILED | 500 | 提示用户检查文件 | "图纸解析失败，请检查文件完整性" |
| 引擎内部错误 | ENGINE_ERROR | 500 | 展示错误+重试按钮 | "系统处理异常，请重试" |
| 授权令牌无效 | AUTH_FAILED | 401 | 重新引导支付 | "授权验证失败，请重新支付" |
| 授权已过期 | TOKEN_EXPIRED | 401 | 重新引导支付 | "支付授权已过期，请重新支付" |
| 文件不存在 | FILE_NOT_FOUND | 404 | 提示重新上传 | "文件已过期，请重新上传" |
| 重构失败 | RECONSTRUCT_FAILED | 500 | 展示错误+重试按钮 | "模型生成失败，请重试" |

### EMA2侧异常处理代码模式

```python
def handle_baa_error(result: dict) -> str:
    """根据error_code返回用户可见的错误信息"""
    error_map = {
        "UNSUPPORTED_FORMAT": "仅支持DXF/DWG格式",
        "FILE_TOO_LARGE": "文件超过50MB限制",
        "PARSE_FAILED": "图纸解析失败，请检查文件完整性",
        "ENGINE_ERROR": "系统处理异常，请重试",
        "AUTH_FAILED": "授权验证失败，请重新支付",
        "TOKEN_EXPIRED": "支付授权已过期，请重新支付",
        "FILE_NOT_FOUND": "文件已过期，请重新上传",
        "RECONSTRUCT_FAILED": "模型生成失败，请重试",
    }
    return error_map.get(result.get("error_code", ""), "未知错误")
```

---

## 5. 完整任务流程

### 5.1 免费审查流程

```
EMA2用户上传图纸
    ↓
EMA2 → POST /deconstruct (文件上传)
    ↓
BAA 解析成功 → 返回 elements + file_id
    ↓
EMA2 展示审查结果给用户
    ↓
用户选择是否继续付费重构
```

### 5.2 付费重构流程

```
用户确认付费
    ↓
EMA2 引导用户完成支付
    ↓
授权代收代付点收款成功 → 生成 auth_token
    ↓
auth_token 传递到 EMA2 后端
    ↓
EMA2 → POST /reconstruct {file_id, auth_token, order_id}
    ↓
BAA 验证 auth_token（HMAC签名 + 有效期 + 配额）
    ↓
验证通过 → BAA执行重构 → 返回 model_file
    ↓
EMA2 展示下载链接 → 用户下载
```

### 5.3 异常重试流程

```
BAA返回异常
    ↓
EMA2 解析 error_code
    ↓
├── AUTH_FAILED / TOKEN_EXPIRED → 重新引导支付
├── FILE_NOT_FOUND → 提示重新上传
├── PARSE_FAILED / ENGINE_ERROR → 展示重试按钮
└── RECONSTRUCT_FAILED → 展示重试按钮
```

---

## 6. 环境配置

### 6.1 EMA2侧环境变量

```bash
# BAA服务地址（必填）
export BAA_API_URL="http://localhost:8000"

# BAA API密钥（必填，由BAA提供）
export BAA_API_KEY="your-api-key-here"

# 超时设置（可选）
export BAA_TIMEOUT_SECONDS=60
export BAA_RECONSTRUCT_TIMEOUT=120

# 最大重试次数（可选）
export BAA_MAX_RETRIES=3
```

### 6.2 BAA侧环境变量

```bash
# API密钥（多个用逗号分隔）
export BAA_API_KEYS="key1,key2"

# 共享密钥（用于auth_token签名验证）
export BAA_AUTH_SECRET="your-shared-secret"

# 服务端口
export BAA_PORT=8000
```

---

## 7. 部署检查清单

| 检查项 | EMA2 | BAA |
|:-------|:----:|:---:|
| 服务运行中 | ✅ | ✅ port 8000 |
| API地址已配置 | `BAA_API_URL` | — |
| API Key已配置 | `BAA_API_KEY` | `BAA_API_KEYS` |
| 共享密钥已配置 | 授权代收代付点 | `BAA_AUTH_SECRET` |
| 跨域支持 | — | CORS ✅ |
| 超时设置合理 | 60s / 120s | 默认60s |

---

## 8. 变更记录

| 版本 | 日期 | 变更内容 |
|:----:|:----:|---------|
| v1.0 | 2026-06-21 | 初始版本，完整对接方案 |

*编制：司军（AI业务助理）*
*日期：2026-06-21*