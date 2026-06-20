# DD-8：API 服务层——详细设计文档（新增）

> **所属阶段：** 工程设计（详细设计）
> **对应架构层：** API 服务层（核心引擎外壳）
> **编制日期：** 2026-06-20（终稿定稿）
> **依据资料：** EMA2 API接口需求文档 v3.0（2026-06-16）
> **前提约束：** BAA不处理定价/支付，仅依据授权代收代付点传输的支付信息提供对应服务

---

## 1. 设计概述

### 1.1 设计目标

将BAA核心引擎（图纸解析→语义识别→原子函数判定→归因分析）封装为标准化HTTP API，与EMA2平台无缝对接。EMA2侧代码零改动。

**核心指标：**
- 接口标准：与EMA2的baa_client.py期望格式完全一致
- EMA2侧改动：零
- 认证方式：Bearer <REDACTED>
- 文件上传：multipart/form-data
- 响应格式：JSON

### 1.2 三种接入方式（按优先级切换）

| 优先级 | 接入方式 | V1.0状态 | 说明 |
|:------:|---------|:--------:|------|
| 1 | **MCP接口** | 🟡 设计完成，V2.0实现 | OpenClaw MCP server |
| 2 | **REST API** | ✅ V1.0实现 | 标准HTTP，EMA2配置环境变量即可 |
| 3 | **OpenClaw Skill** | 🟡 设计完成，V2.0实现 | SKILL.md + 脚本 |

---

## 2. 接入架构

### 2.1 调用链

```
EMA2前端 → EMA2后端(7188) → BAA Client → BAA API 服务
                                              │
                         ┌────────────────────┼────────────────────┐
                         ▼                    ▼                    ▼
                    MCP Server          REST API            Skill 脚本
                    (V2.0)              (V1.0)              (V2.0)
                         │                    │                    │
                         └────────────────────┼────────────────────┘
                                              ▼
                                      BAA 核心引擎
                          (图纸解析→语义识别→原子函数→归因分析)
```

### 2.2 REST API 接入（V1.0）

EMA2侧操作：
```bash
# 配置环境变量即可，零代码改动
export BAA_API_BASE=https://baa-service.example.com
export BAA_API_KEY=sk-baa-xxxxx
```

BAA侧需要提供：
1. API Base URL
2. API Key 生成+验证
3. 3个HTTP接口（/deconstruct, /reconstruct, /order/{id}）

### 2.3 MCP 接入（V2.0，设计先行）

```
BAA MCP Server (streamable-http)
├── 工具1: baa_deconstruct → 对应 /deconstruct
├── 工具2: baa_reconstruct → 对应 /reconstruct
└── 自动注册到 OpenClaw MCP client

EMA2侧操作:
openclaw mcp add baa \
  --url https://baa-service.example.com/mcp \
  --transport streamable-http \
  --header "Authorization: Bearer sk-baa-xxxxx" \
  --timeout 120
```

### 2.4 Skill 接入（V2.0，设计先行）

```
baa-blueprint/
├── SKILL.md              # Skill 说明文档
├── scripts/
│   ├── deconstruct.py   # 调用 BAA REST API 进行解构
│   └── reconstruct.py   # 调用 BAA REST API 进行重构
└── README.md
```

---

## 3. 接口详细设计

### 3.1 接口清单

| 接口 | 方法 | 功能 | 计费判断 | V1.0状态 | 优先级 |
|------|------|------|---------|:--------:|:-----:|
| /deconstruct | POST | 图纸解构，提取构件信息 | 免费 | ✅ 真实 | P0 |
| /reconstruct | POST | 基于解构结果生成BIM模型 | 需验证授权 | ✅ 真实(MVP可mock) | P0 |
| /order/{order_id} | GET | 查询重构任务状态 | — | ✅ 真实(MVP可mock) | P1 |
| /health | GET | 健康检查 | — | ✅ 真实 | P1 |

### 3.2 接口 1：/deconstruct（图纸解构，免费）

```python
# 接口定义
POST {BAA_API_BASE}/deconstruct
Authorization: Bearer {api_key}
Content-Type: multipart/form-data

Request:
  file: <图纸文件二进制>

Response (200):
{
  "status": "success",
  "elements": [
    {"type": "wall", "count": 12, "total_length": 45.6},
    {"type": "column", "count": 8, "total_volume": 15.2},
    {"type": "beam", "count": 16, "total_length": 62.4},
    {"type": "slab", "count": 4, "total_area": 320.0},
    {"type": "door", "count": 10, "note": "含防火门2个"},
    {"type": "window", "count": 8, "total_area": 45.0},
    {"type": "stair", "count": 2, "note": "疏散楼梯"},
    {"type": "elevator", "count": 3, "note": "含消防电梯1个"}
  ],
  "confidence": 0.92,
  "file_id": "baa-file-xxxxx",
  "processing_time_ms": 3500
}

Error Response (400):
{
  "status": "error",
  "error_code": "UNSUPPORTED_FORMAT",
  "message": "不支持的文件格式。支持: pdf, dwg, dxf, jpg, png"
}

Error Response (401):
{
  "status": "error",
  "error_code": "INVALID_API_KEY",
  "message": "API Key 无效"
}

Error Response (500):
{
  "status": "error",
  "error_code": "PROCESSING_FAILED",
  "message": "图纸处理失败，请检查文件是否损坏"
}
```

**说明：**
- 免费接口，不限次数
- 支持文件格式：PDF / DWG / DXF / JPG / PNG（扩展支持列表）
- 返回 file_id 用于后续 /reconstruct 接口关联
- elements 中 type 字段取值：wall, column, beam, slab, door, window, stair, elevator, fire_door, corridor
- confidence 是整体识别置信度 0-1
- 图纸解构只做基础构件提取，不做合规审查（合规审查由BAA Web端提供）

### 3.3 接口 2：/reconstruct（BIM重构，需授权验证）

```python
# 接口定义
POST {BAA_API_BASE}/reconstruct
Authorization: Bearer {api_key}
Content-Type: application/json

Request:
{
  "order_id": "order-ema2-xxxxx",       # 来自EMA2的订单号
  "auth_token": "auth-baa-token-xxxxx", # 授权代收代付点传输的支付授权令牌
  "file_id": "baa-file-xxxxx",          # 来自 /deconstruct 的 file_id
  "elements": [                         # 可选，传入则使用此数据，不传则用 file_id 关联的数据
    {"type": "wall", "count": 12, "total_length": 45.6}
  ],
  "options": {
    "lod": 300,                          # LOD 等级 (100/200/300)
    "format": "ifc",                     # 输出格式 (ifc/obj/fbx)
    "include_reinforcement": false       # 是否包含配筋信息
  }
}

Response (200) - 同步完成:
{
  "status": "success",
  "order_id": "order-ema2-xxxxx",
  "baa_order_id": "baa-order-yyyyy",
  "model_url": "https://baa-service.com/models/baa-order-yyyyy/model.ifc",
  "elements_count": 40,
  "processing_time_ms": 15000,
  "file_size_mb": 2.5,
  "valid_until": "2026-07-20T09:26:00Z"  # 下载链接有效期
}

Response (202) - 异步处理中:
{
  "status": "processing",
  "order_id": "order-ema2-xxxxx",
  "baa_order_id": "baa-order-yyyyy",
  "message": "正在处理中，请通过 GET /order/{baa_order_id} 查询进度",
  "estimated_time_ms": 30000
}

Response (402) - 授权验证失败:
{
  "status": "error",
  "error_code": "AUTH_FAILED",
  "message": "支付授权验证失败，请确认订单已支付"
}

Response (403) - 授权过期:
{
  "status": "error",
  "error_code": "AUTH_EXPIRED",
  "message": "授权令牌已过期，请重新支付"
}
```

**说明：**
- 这是需验证授权的接口
- **BAA不做支付处理**，仅验证来自授权代收代付点的 auth_token 有效性
- auth_token 由EMA2支付流程完成后生成并传给BAA
- 如果重构耗时较长，返回 202 + baa_order_id
- model_url 是生成的BIM模型文件下载地址，含有效期
- options 参数可选，有默认值（LOD 300, format ifc）

### 3.4 接口 3：/order/{order_id}（订单状态查询）

```python
# 接口定义
GET {BAA_API_BASE}/order/{baa_order_id}
Authorization: Bearer {api_key}

Response (200) - 已完成:
{
  "status": "completed",
  "order_id": "order-ema2-xxxxx",
  "baa_order_id": "baa-order-yyyyy",
  "model_url": "https://baa-service.com/models/baa-order-yyyyy/model.ifc",
  "progress": 100,
  "processing_time_ms": 15000,
  "file_size_mb": 2.5
}

Response (200) - 进行中:
{
  "status": "processing",
  "order_id": "order-ema2-xxxxx",
  "baa_order_id": "baa-order-yyyyy",
  "progress": 65,
  "estimated_remaining_ms": 10000
}

Response (200) - 失败:
{
  "status": "failed",
  "order_id": "order-ema2-xxxxx",
  "baa_order_id": "baa-order-yyyyy",
  "error": "模型生成失败：图纸数据不完整",
  "progress": 0
}

Response (404):
{
  "status": "error",
  "error_code": "ORDER_NOT_FOUND",
  "message": "订单不存在"
}
```

### 3.5 接口 4：/health（健康检查）

```python
GET {BAA_API_BASE}/health

Response (200):
{
  "status": "ok",
  "version": "1.0.0",
  "uptime_seconds": 86400,
  "engine_status": "ready",
  "supported_formats": ["pdf", "dwg", "dxf", "jpg", "png"],
  "api_version": "v1"
}
```

---

## 4. 授权验证机制（新增——依据Master决策）

### 4.1 设计原则

| 原则 | 说明 |
|------|------|
| **BAA不处理支付** | 定价/收款由EMA2或其他授权代收代付点处理 |
| **仅验证授权** | BAA接收 auth_token 后，验证其有效性再提供服务 |
| **无状态设计** | auth_token 自包含验证信息，BAA不维护用户状态 |
| **可撤销** | 授权代收代付点可随时撤销已签发的 token |

### 4.2 授权流程

```
用户 → EMA2
  │
  ├── 用户在EMA2完成支付（EMA2处理定价/收款）
  │
  ▼
EMA2支付系统
  │
  ├── EMA2确认支付成功
  ├── 生成 auth_token（含订单ID、服务类型、有效期限、签名）
  │
  ▼
EMA2 → BAA
  │
  ├── POST /reconstruct 时携带 auth_token
  │
  ▼
BAA 授权验证模块
  │
  ├── 验证 auth_token 签名（HMAC-SHA256，共享密钥）
  ├── 验证有效期限
  ├── 验证服务类型匹配（deconstruct/reconstruct）
  ├── 验证是否已被撤销（可选，查撤销列表）
  │
  ├── 验证通过 → 执行服务 → 返回结果
  └── 验证失败 → 返回 402/403 错误
```

### 4.3 auth_token 格式

```json
{
  "version": 1,
  "order_id": "order-ema2-xxxxx",
  "service": "reconstruct",
  "issued_at": "2026-06-20T09:00:00Z",
  "expires_at": "2026-06-20T10:00:00Z",
  "quota": {
    "max_requests": 1,
    "max_file_size_mb": 50
  },
  "client_id": "ema2-platform"
}
```

传输方式：auth_token 作为 JWT 格式传递（Header.Payload.Signature）

```python
# 签名算法
import hmac
import hashlib
import json

SHARED_SECRET = os.getenv("BAA_AUTH_SECRET", "")

def generate_auth_token(payload: dict) -> str:
    """授权代收代付点生成 auth_token"""
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = base64url_encode(json.dumps(header))
    payload_b64 = base64url_encode(json.dumps(payload))
    signing_input = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        SHARED_SECRET.encode(),
        signing_input.encode(),
        hashlib.sha256
    ).digest()
    sig_b64 = base64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def verify_auth_token(token: str) -> dict:
    """BAA验证 auth_token"""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(
            SHARED_SECRET.encode(),
            signing_input.encode(),
            hashlib.sha256
        ).digest()
        if base64url_decode(sig_b64) != expected_sig:
            raise AuthError("签名无效")
        
        payload = json.loads(base64url_decode(payload_b64))
        
        # 验证有效期
        now = datetime.utcnow()
        if now > parse_iso8601(payload["expires_at"]):
            raise AuthError("授权已过期")
        
        return payload
    except Exception as e:
        raise AuthError(f"授权验证失败: {str(e)}")
```

### 4.4 共享密钥管理

| 密钥 | 用途 | 谁持有 | 轮换策略 |
|------|------|--------|---------|
| BAA_AUTH_SECRET | auth_token 签名/验证 | EMA2 + BAA | 每90天轮换，旧密钥48h宽限期 |
| BAA_API_KEY | REST API 接口认证 | BAA + 授权客户端 | 按客户端吊销/重发 |

### 4.5 免费额度处理

每月前3次BAA重构免费：由EMA2侧控制，BAA不做免费额度判断。

```
EMA2侧逻辑：
1. 检查用户本月使用次数（EMA2数据库）
2. 如果≤3次 → EMA2生成免费 auth_token（service="reconstruct_free"）
3. 如果>3次 → 要求用户先支付，支付完成后生成收费 auth_token
4. BAA收到 auth_token，验证有效即可，不关心是否免费
```

---

## 5. 文件格式支持扩展

### 5.1 支持格式列表

| 格式 | V1.0支持 | 处理方式 | 备注 |
|------|:--------:|---------|------|
| DXF | ✅ | ezdxf 原生解析 | 基础格式 |
| DWG | 🟡 | LibreDWG WASM 转换 → ezdxf | 可能部分失真 |
| PDF | 🟡 | 先用 PyMuPDF 提取文本+尺寸 | 仅提取文本/标注 |
| JPG | 🟡 | 仅返回"不支持矢量图纸"，建议上传DXF/DWG | 用于反馈引导 |
| PNG | 🟡 | 同上 | — |

**V1.0 /deconstruct 真实支持的格式：DXF（主力）、DWG（转换后有限支持）**
PDF/JPG/PNG → 返回明确的错误信息，引导用户上传矢量格式。

```python
SUPPORTED_FORMATS = {
    "dxf": {"parser": "ezdxf", "type": "vector", "v1_support": True},
    "dwg": {"parser": "libredwg_wasm", "type": "vector", "v1_support": True},
    "pdf": {"parser": "pymupdf", "type": "raster", "v1_support": False, "fallback_msg": "请上传DXF/DWG格式图纸"},
    "jpg": {"parser": None, "type": "image", "v1_support": False, "fallback_msg": "请上传DXF/DWG格式矢量图纸"},
    "png": {"parser": None, "type": "image", "v1_support": False, "fallback_msg": "请上传DXF/DWG格式矢量图纸"},
}

def get_deconstruct_response(file_path: str, file_type: str) -> dict:
    fmt_info = SUPPORTED_FORMATS.get(file_type.lower())
    if not fmt_info:
        return {
            "status": "error",
            "error_code": "UNSUPPORTED_FORMAT",
            "message": f"不支持的文件格式: {file_type}。支持: dxf, dwg"
        }
    
    if not fmt_info["v1_support"]:
        return {
            "status": "error",
            "error_code": "FORMAT_NOT_YET_SUPPORTED",
            "message": fmt_info["fallback_msg"]
        }
    
    # 执行图纸解析
    return process_drawing(file_path, fmt_info["parser"])
```

---

## 6. 文件管理

### 6.1 file_id 生成

```python
import uuid
import os

FILE_STORAGE_PATH = "/data/baa/files/"
MODEL_STORAGE_PATH = "/data/baa/models/"

def generate_file_id() -> str:
    return f"baa-file-{uuid.uuid4().hex[:12]}"

def store_uploaded_file(file_content: bytes, file_id: str, extension: str):
    path = os.path.join(FILE_STORAGE_PATH, f"{file_id}.{extension}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(file_content)
    return path
```

### 6.2 文件存储架构

| 存储类型 | 路径 | 清理策略 | V1.0方案 |
|---------|------|---------|---------|
| 上传图纸 | /data/baa/files/{file_id}.{ext} | 7天后自动清理 | 本地文件系统 |
| 模型输出 | /data/baa/models/{order_id}/model.ifc | 30天后自动清理 | 本地文件系统 |
| 临时文件 | /tmp/baa/{file_id}/ | 处理完成后清理 | tempfile |

### 6.3 文件服务

```python
from fastapi.staticfiles import StaticFiles

# 提供模型下载
app.mount("/models", StaticFiles(directory="/data/baa/models"), name="models")

# 生成下载URL
def get_model_url(order_id: str, base_url: str) -> str:
    return f"{base_url}/models/{order_id}/model.ifc"
```

---

## 7. 认证与安全

### 7.1 API Key 认证

```python
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

API_KEYS = set()  # 从环境变量或配置文件加载

security = HTTPBearer()

def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """验证 Bearer Token（API Key）"""
    api_key = credentials.credentials
    if api_key not in API_KEYS:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "error_code": "INVALID_API_KEY", "message": "API Key 无效"}
        )
    return api_key

@app.post("/deconstruct")
async def deconstruct(
    file: UploadFile = File(...),
    api_key: str = Depends(verify_api_key)
):
    # ...
```

### 7.2 速率限制

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/deconstruct")
@limiter.limit("60/minute")  # /deconstruct 60次/分钟
async def deconstruct(...):
    ...

@app.post("/reconstruct")
@limiter.limit("10/minute")  # /reconstruct 10次/分钟
async def reconstruct(...):
    ...
```

### 7.3 文件大小限制

| 限制项 | 限制值 | V1.0 |
|-------|--------|:----:|
| 单文件最大 | 50MB | ✅ 配置项 |
| 单次请求超时 | 120秒 | ✅ 配置项 |
| 解构处理超时 | 30秒 | ✅ 配置项 |
| 重构处理超时 | 120秒 | ✅ 配置项 |

---

## 8. MCP Server 设计（V2.0）

### 8.1 MCP Server 定义

```python
# baa_mcp_server.py
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

class BAAMCPServer:
    """BAA MCP Server"""
    
    async def list_tools(self) -> list[Tool]:
        return [
            Tool(
                name="baa_deconstruct",
                description="解构工程图纸，识别墙、柱、梁、板、门、窗、楼梯等构件",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "图纸文件路径"}
                    },
                    "required": ["file_path"]
                }
            ),
            Tool(
                name="baa_reconstruct",
                description="基于构件信息生成 BIM 模型（需授权验证）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_id": {"type": "string", "description": "解构接口返回的 file_id"},
                        "auth_token": {"type": "string", "description": "支付授权令牌"},
                        "elements": {"type": "array", "description": "构件列表（可选）"},
                        "options": {"type": "object", "description": "重构参数"}
                    },
                    "required": ["file_id", "auth_token"]
                }
            )
        ]
    
    async def call_tool(self, name: str, arguments: dict) -> list[TextContent]:
        if name == "baa_deconstruct":
            result = await call_baa_deconstruct(arguments["file_path"])
            return [TextContent(type="text", text=json.dumps(result))]
        elif name == "baa_reconstruct":
            result = await call_baa_reconstruct(
                file_id=arguments["file_id"],
                auth_token=arguments["auth_token"],
                elements=arguments.get("elements"),
                options=arguments.get("options")
            )
            return [TextContent(type="text", text=json.dumps(result))]
```

### 8.2 MCP 启动方式

```bash
# Streamable HTTP 方式
python baa_mcp_server.py --transport streamable-http --port 8080

# Stdio 方式
python baa_mcp_server.py --transport stdio
```

---

## 9. OpenClaw Skill 设计（V2.0）

### 9.1 目录结构

```
baa-blueprint-skill/
├── SKILL.md
├── scripts/
│   ├── deconstruct.py      # 调用BAA REST API进行解构
│   ├── reconstruct.py      # 调用BAA REST API进行重构
│   ├── baa_client.py       # BAA API 客户端封装
│   └── config.py           # 配置（API Base URL, API Key）
└── README.md
```

### 9.2 SKILL.md

```markdown
---
name: baa-blueprint
description: BAA 蓝图重构能力，包含图纸解构和 BIM 模型生成
---

# BAA 蓝图重构 Skill

## 使用场景
当用户请求图纸解构、BIM 模型生成、蓝图重构时使用本 Skill。

## 前置条件
- 配置 BAA_API_BASE 和 BAA_API_KEY（config.py）
- 确保 BAA 服务已启动

## 解构（免费）
python scripts/deconstruct.py <file_path>

## 重构（需授权验证）
python scripts/reconstruct.py <file_id> <auth_token> [elements_json]

## 授权说明
BAA 不处理支付，重构服务需要有效的 auth_token。
auth_token 由 EMA2 平台支付完成后生成并传递。
```

---

## 10. 交付物清单

| 交付物 | 格式 | 说明 | 工作量 |
|--------|------|------|:------:|
| `baa_api_server.py` | Python FastAPI | API服务主程序（3个端点+认证+限流） | 2天 |
| `auth_verifier.py` | Python | auth_token 验证模块（HMAC-SHA256） | 0.5天 |
| `file_manager.py` | Python | 文件上传/存储/清理管理 | 0.5天 |
| `format_detector.py` | Python | 文件格式检测+支持列表 | 0.5天 |
| `baa_mcp_server.py` | Python | MCP Server（V2.0） | 2天 |
| `baa-blueprint-skill/` | 目录 | Skill 包（V2.0） | 1天 |
| `api_docs.md` | Markdown | API接口文档 | 0.5天 |
| `config.py` (API相关) | Python | API Key + Auth Secret 配置 | 0.5天 |

**总新增工作量：约 7天（V1.0 核心 API 部分约 4天，含文档）**

---

*编制：司军（AI业务助理）*
*日期：2026-06-20（终稿定稿）*
*依据：EMA2 API接口需求文档 v3.0 + Master决策（BAA不处理定价/支付，仅验证授权）*
*V1.0 实现：REST API + 授权验证 + 文件管理*
*V2.0 预留：MCP Server + Skill 包（设计先行）*