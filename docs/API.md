# BAA API 接口文档

> BAA (Building Audit AI) — 建筑图纸AI审查服务
> 版本: v1.7.6 | 规范: GB50016-2014 (建筑设计防火规范)

---

## 基础信息

| 项目 | 值 |
|------|-----|
| 基础URL | `http://localhost:8000` |
| 认证方式 | Bearer Token (Header: `Authorization: Bearer <api_key>`) |
| 内容类型 | `application/json` |
| 支持格式 | `.dxf`, `.dwg` |

---

## 端点列表

### 1. 健康检查

```
GET /health
```

**返回:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "engine_status": "ready",
  "supported_formats": ["dwg", "dxf"],
  "api_version": "v1"
}
```

---

### 2. 图纸解析与审查（核心端点）

```
POST /deconstruct
Content-Type: multipart/form-data

参数:
  file          File     (必填) DXF/DWG图纸文件
  building_type string   (可选) "civil" 民用 | "industrial" 工业，默认civil
  use_yolo      boolean  (可选) 是否启用YOLO图元检测增强，默认false
```

**处理流程:**
```
文件上传 → DXF/DWG解析 → 语义分析(18类实体识别)
                           ├─ [可选] YOLO检测增强
                           └─ [自动] DIMENSION尺寸注入
         → 规范判定(19条GB50016规范) → 去重 → 返回结果
```

**返回:**
```json
{
  "status": "success",
  "elements": [
    {
      "type": "staircase",
      "count": 1,
      "bbox": { "x": 0, "y": 0, "width": 10, "height": 5 },
      "properties": { "width": 1.5, "clear_width": 1.5, "_dimension_source": "dimension" }
    }
  ],
  "summary": {
    "total_violations": 5,
    "warnings": 0,
    "critical": 3,
    "total_checks": 742
  },
  "findings": [
    {
      "finding_id": "baa-finding-xxx",
      "clause_id": "GB50016-5.5.18",
      "clause_title": "疏散楼梯净宽判定",
      "entity_type": "staircase",
      "result": "FAIL",
      "severity": "critical",
      "extracted_value": 0.8,
      "required_value": 1.2,
      "is_duplicate": false
    }
  ],
  "total_checks": 742,
  "file_id": "baa-file-xxx",
  "building_type": "civil",
  "processing_time_ms": 850
}
```

---

### 3. 图纸渲染

```
GET /render/{file_id}
```

**返回:** SVG格式图纸（`Content-Type: image/svg+xml`）

---

### 4. 审查数据提交（AI审图用）

```
POST /review-from-data
Content-Type: application/json

{
  "entities": [ ... ],    // 实体列表（从deconstruct获取）
  "building_type": "civil"
}
```

**返回:**
```json
{
  "status": "completed",
  "details": [ ... ],
  "corrections": [ ... ],
  "raw_result": { ... }   // 完整结果供对比重构消费
}
```

---

### 5. 图纸重构（需授权）

```
POST /reconstruct
Content-Type: application/json

{
  "file_id": "baa-file-xxx",
  "order_id": "xxx",
  "auth_token": "xxx"
}
```

**返回:** 重构后的BIM模型URL

---

### 6. 订单状态查询

```
GET /order/{order_id}
```

---

## 错误码

| HTTP状态 | error_code | 说明 |
|----------|------------|------|
| 401 | - | API密钥无效或缺失 |
| 402 | AUTH_FAILED | 授权验证失败（重构需要） |
| 404 | FILE_NOT_FOUND | 文件不存在 |
| 422 | - | 请求参数错误 |

---

## 调用示例 (Python)

```python
import requests

API_KEY = "your-api-key-here"
BASE = "http://localhost:8000"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# 上传并审查图纸
with open("drawing.dxf", "rb") as f:
    r = requests.post(
        f"{BASE}/deconstruct?building_type=civil",
        files={"file": f},
        headers=HEADERS,
    )
    result = r.json()
    print(f"违规: {result['summary']['total_violations']}项")
```

## 调用示例 (cURL)

```bash
# 上传审查
curl -X POST http://localhost:8000/deconstruct \\
  -H "Authorization: Bearer your-key" \\
  -F "file=@drawing.dxf" \\
  -F "building_type=civil"

# 图纸渲染
curl http://localhost:8000/render/baa-file-xxx \\
  -H "Authorization: Bearer your-key" \\
  -o preview.svg
```
