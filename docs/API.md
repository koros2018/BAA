# BAA API 接口文档

> BAA (Blueprint AI Agent) — 建筑图纸AI审查服务
> 版本: v1.12.0 | 规范: GB50016-2014 (建筑设计防火规范)
> 原子函数: 30/30 (10 L1 + 9 L2 + 11 L3) | 规范条款: 31条

---

## 基础信息

| 项目 | 值 |
|------|-----|
| 基础URL | `http://localhost:8000` |
| 认证方式 | Bearer Token (Header: `Authorization: Bearer <api_key>`) |
| 开发模式 | `BAA_API_KEY` 为空时不校验，直接放行 |
| 内容类型 | `application/json` |
| 支持格式 | `.dxf`, `.dwg` |
| 交互文档 | `http://localhost:8000/docs` (Swagger UI) |

---

## 端点列表

### 1. 健康检查

```
GET /health
```

获取服务状态及各子系统健康情况。

**返回:**
```json
{
  "status": "ok",
  "version": "1.12.0",
  "engine_status": "ready",
  "supported_formats": ["dxf", "dwg"],
  "subsystems": {
    "engine": {"status": "ok"},
    "spec_repository": {"status": "ok"},
    "drawing_parser": {"status": "ok"},
    "yolo_integrator": {"status": "ok", "info": "就绪"}
  }
}
```

---

### 2. 图纸解析（解构）

```
POST /deconstruct
```

上传 DXF/DWG 图纸并解析为结构化实体数据。

**请求:** `multipart/form-data`
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | DXF/DWG 文件（最大50MB）|
| building_type | string | 否 | `civil`（民用，默认）/ `industrial`（工业）|
| use_yolo | boolean | 否 | 是否启用 YOLO 图元检测增强 |

**返回:**
```json
{
  "file_id": "baa-file-xxx",
  "status": "completed",
  "elements": [{"id": "...", "type": "staircase", ...}],
  "findings": [{"clause_id": "GB50016-5.5.18", "result": "FAIL", ...}]
}
```

---

### 3. 图纸合规审查

```
POST /review
```

对已上传解析的图纸执行完整合规审查。

**请求:**
```json
{
  "file_id": "baa-file-xxx",
  "building_type": "civil"
}
```

**返回:** 审查报告（含概要、违规详情、修正建议、可视化数据）

---

### 4. 基于数据的审查

```
POST /review-from-data
```

直接传入实体数据进行审查（无需预上传文件）。

**请求:**
```json
{
  "entities": [{"id": "S1", "type": "staircase", "properties": {...}}],
  "building_type": "civil"
}
```

**返回:**
```json
{
  "status": "success",
  "summary": {"total_violations": 3, "critical": 1, "major": 1, "minor": 1},
  "details": [{"clause_id": "...", "severity": "critical", ...}],
  "corrections": [...]
}
```

---

### 5. 图纸重构

```
POST /reconstruct
```

根据审查结果生成修正后的图纸。

**请求:**
```json
{
  "original_elements": [...],
  "corrections": [...],
  "building_type": "civil"
}
```

**返回:** 重构后的实体数据及修正说明

---

### 6. 查询订单/任务

```
GET /order/{order_id}
```

查询异步处理任务的执行状态。

---

### 7. 图纸渲染

```
GET /render/{file_id}
```

将解析后的图纸渲染为 SVG 预览图。

**认证:** 需要有效 API Key

---

## 密钥管理（admin 端点）

所有 admin 端点需要在 `Authorization` Header 中携带管理令牌。
开发模式（`BAA_API_KEY` 为空）下不校验。

### 7.1 创建密钥

```
POST /admin/keys
```

**请求:**
```json
{
  "label": "EMA2对接",
  "permission": "write",
  "ttl_days": 90
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| label | string | 是 | 密钥名称/标签 |
| permission | string | 否 | 权限: `admin` / `write` / `read` / `limited`（默认 `read`）|
| ttl_days | int | 否 | 有效期（天），默认 90 |

**返回:**
```json
{
  "status": "success",
  "key": {"id": "...", "label": "EMA2对接", "permission": "write",
          "key_prefix": "baa_...", "created_at": "..."},
  "raw_key": "baa_xxxxx"  // ⚠️ 仅返回一次！
}
```

### 7.2 密钥列表

```
GET /admin/keys
```

返回所有密钥及用量统计。

### 7.3 撤销密钥

```
POST /admin/keys/{key_id}/revoke
```

### 7.4 轮换密钥

```
POST /admin/keys/{key_id}/rotate
```

生成新密钥值，旧密钥进入轮换宽限期。

### 7.5 删除密钥

```
DELETE /admin/keys/{key_id}
```

永久删除（不可恢复）。

### 7.6 用量统计

```
GET /admin/keys/stats
```

### 7.7 验证密钥

```
POST /admin/keys/verify
```

**请求:**
```json
{
  "key": "baa_xxxxx"
}
```

**返回:**
```json
{
  "status": "success",
  "valid": true,
  "key_info": {"label": "...", "permission": "write", ...}
}
```

### 7.8 引导密钥

```
GET /admin/bootstrap-key
```

免认证端点，供前端密钥管理页初始化时获取管理令牌。

**返回:**
```json
{
  "status": "success",
  "admin_key": "xxx",
  "mode": "production"
}
```

---

## 认证与鉴权

### 权限等级

| 等级 | 说明 | 可用端点 |
|------|------|---------|
| admin | 完全控制 | 所有端点 |
| write | 读写访问 | `/deconstruct`, `/review`, `/review-from-data`, `/reconstruct` |
| read | 只读 | `/health`, `/order/{id}`, `/render/{id}` |
| limited | 受限 | `/health` |

### 使用方式

```bash
# Header 方式（推荐）
curl -H "Authorization: Bearer baa_xxxxx" http://localhost:8000/health

# Query 参数方式
curl "http://localhost:8000/health?authorization=baa_xxxxx"
```

---

## 错误码

| HTTP 状态码 | 说明 |
|------------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未提供 API Key |
| 403 | 权限不足或密钥已过期/撤销 |
| 404 | 资源不存在 |
| 422 | 请求体格式错误 |
| 429 | 请求过于频繁（限流）|
| 500 | 服务端错误 |

---

## 快速开始

```bash
# 1. 启动服务
python src/api/baa_api.py

# 2. 健康检查
curl http://localhost:8000/health

# 3. 上传并审查图纸
curl -X POST http://localhost:8000/deconstruct \
  -H "Authorization: Bearer your-key" \
  -F "file=@drawing.dxf" \
  -F "building_type=civil"

# 4. 图纸渲染
curl http://localhost:8000/render/baa-file-xxx \
  -H "Authorization: Bearer your-key" \
  -o preview.svg
```