# DD-9：MCP与OpenClaw Skill接入方案——详细设计文档（新增）

> **所属阶段：** 工程设计（详细设计）
> **对应架构层：** API 服务层 → 三种接入方式之二
> **编制日期：** 2026-06-20（终稿定稿）
> **依据资料：** EMA2 API接口需求文档 v3.0 第5章（方案B MCP + 方案C Skill）
> **前提约束：** V1.0实现REST API，MCP和Skill设计先行，V2.0实现

---

## 1. 设计概述

### 1.1 三种接入方式优先级

| 优先级 | 接入方式 | V1.0状态 | 实现时间 | EMA2侧改动 |
|:------:|---------|:--------:|---------|:----------:|
| 1 | **REST API** | ✅ 已实现 | V1.0 | 零，仅配置环境变量 |
| 2 | **MCP接口** | 🟡 设计完成 | V2.0 | 需注册MCP server |
| 3 | **OpenClaw Skill** | 🟡 设计完成 | V2.0 | 需安装Skill包 |

### 1.2 设计目标

1. **MCP接口**：将BAA核心能力封装为MCP Server，EMA2通过OpenClaw MCP Client自动发现和调用
2. **OpenClaw Skill**：将BAA核心能力封装为可复用的Skill包，EMA2安装后agent自动读取使用

---

## 2. MCP接口方案

### 2.1 什么是MCP

MCP（Model Context Protocol）是AI agent调用外部工具的标准化协议。OpenClaw原生支持MCP Client，可以连接任何MCP Server。

**BAA的MCP Server定位：**
- BAA作为MCP Server提供2个工具（baa_deconstruct, baa_reconstruct）
- EMA2通过OpenClaw MCP Client注册BAA Server
- Agent运行时自动发现工具，在需要时调用

### 2.2 MCP Server架构

```
BAA MCP Server
├── 传输层
│   ├── Streamable HTTP（推荐）
│   └── Stdio（备用）
├── 工具注册表
│   ├── baa_deconstruct → 调用BAA核心引擎解构
│   └── baa_reconstruct → 调用BAA核心引擎重构
├── 认证层
│   ├── Bearer Token（API Key验证）
│   └── auth_token 转发（重构需授权验证）
└── 内部调用
    └── BAA REST API（本地调用，跳过网络）
```

### 2.3 MCP工具定义

#### 工具1：baa_deconstruct

```json
{
  "name": "baa_deconstruct",
  "description": "解构工程图纸，识别墙、柱、梁、板、门、窗、楼梯、电梯等构件，返回结构化数据。此工具免费使用。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "file_path": {
        "type": "string",
        "description": "图纸文件路径（支持 dxf/dwg/pdf/jpg/png，推荐 dxf）"
      }
    },
    "required": ["file_path"]
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "status": {"type": "string"},
      "elements": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "type": {"type": "string", "description": "构件类型: wall/column/beam/slab/door/window/stair/elevator"},
            "count": {"type": "integer"},
            "total_length": {"type": "number"},
            "total_volume": {"type": "number"},
            "total_area": {"type": "number"}
          }
        }
      },
      "confidence": {"type": "number"},
      "file_id": {"type": "string"}
    }
  }
}
```

#### 工具2：baa_reconstruct

```json
{
  "name": "baa_reconstruct",
  "description": "基于解构结果生成 BIM 模型。此工具需要有效的授权令牌（auth_token），授权令牌由支付完成后生成。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "file_id": {
        "type": "string",
        "description": "解构接口返回的 file_id"
      },
      "auth_token": {
        "type": "string",
        "description": "授权代收代付点生成的支付授权令牌（JWT格式）"
      },
      "elements": {
        "type": "array",
        "description": "构件列表（可选，不传则使用 file_id 关联数据）",
        "items": {
          "type": "object"
        }
      },
      "options": {
        "type": "object",
        "description": "重构参数（可选）",
        "properties": {
          "lod": {"type": "integer", "description": "LOD等级: 100/200/300"},
          "format": {"type": "string", "description": "输出格式: ifc/obj/fbx"},
          "include_reinforcement": {"type": "boolean"}
        }
      }
    },
    "required": ["file_id", "auth_token"]
  }
}
```

### 2.4 MCP Server 实现

```python
# baa_mcp_server.py
"""
BAA MCP Server - 将BAA图纸解构和BIM重构能力封装为MCP工具

启动方式：
  # Streamable HTTP（推荐，适用于远程部署）
  python baa_mcp_server.py --transport streamable-http --port 8080
  
  # Stdio（适用于本地或容器内）
  python baa_mcp_server.py --transport stdio
"""

import json
import os
import asyncio
from typing import Any
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
from mcp.server.lowlevel.helper_types import ReadResourceContents

# BAA核心引擎
from baa_engine import BAAEngine
from auth_verifier import verify_auth_token

engine = BAAEngine()

class BAAMCPServer:
    """BAA MCP Server"""
    
    def __init__(self):
        self.server = Server("baa-blueprint")
        
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="baa_deconstruct",
                    description="解构工程图纸，识别墙、柱、梁、板、门、窗、楼梯、电梯等构件",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string", 
                                "description": "图纸文件路径"
                            }
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
                            "file_id": {
                                "type": "string",
                                "description": "解构接口返回的 file_id"
                            },
                            "auth_token": {
                                "type": "string",
                                "description": "支付授权令牌"
                            },
                            "elements": {
                                "type": "array",
                                "description": "构件列表（可选）"
                            },
                            "options": {
                                "type": "object",
                                "description": "重构参数"
                            }
                        },
                        "required": ["file_id", "auth_token"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            if name == "baa_deconstruct":
                result = await engine.deconstruct(arguments["file_path"])
                return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
            
            elif name == "baa_reconstruct":
                # 验证授权
                auth_payload = verify_auth_token(arguments["auth_token"])
                if auth_payload is None:
                    return [TextContent(
                        type="text", 
                        text=json.dumps({
                            "status": "error",
                            "error_code": "AUTH_FAILED",
                            "message": "授权验证失败"
                        }, ensure_ascii=False)
                    )]
                
                result = await engine.reconstruct(
                    file_id=arguments["file_id"],
                    elements=arguments.get("elements"),
                    options=arguments.get("options"),
                    auth_payload=auth_payload
                )
                return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
            
            else:
                raise ValueError(f"未知工具: {name}")
    
    async def run_stdio(self):
        """通过 stdio 运行 MCP Server"""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="baa-blueprint",
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    
    async def run_http(self, host: str = "0.0.0.0", port: int = 8080):
        """通过 Streamable HTTP 运行 MCP Server"""
        from mcp.server.http import run_server
        await run_server(self.server, host=host, port=port)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="BAA MCP Server")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    
    server = BAAMCPServer()
    
    if args.transport == "stdio":
        asyncio.run(server.run_stdio())
    else:
        asyncio.run(server.run_http(host=args.host, port=args.port))
```

### 2.5 EMA2侧注册方式

```bash
# 方式A：Streamable HTTP（推荐，远程部署）
openclaw mcp add baa \
  --url https://baa-service.example.com/mcp \
  --transport streamable-http \
  --header "Authorization: Bearer ***" \
  --timeout 120

# 方式B：Stdio（本地或容器）
openclaw mcp add baa \
  --command python \
  --arg /path/to/baa_mcp_server.py \
  --arg --transport \
  --arg stdio \
  --timeout 120

# 查看已注册的工具
openclaw mcp tools baa

# 测试工具调用
openclaw mcp call baa baa_deconstruct '{"file_path": "/path/to/drawing.dxf"}'
```

### 2.6 MCP Server部署要求

| 要求项 | 说明 |
|-------|------|
| Python版本 | 3.10+ |
| 依赖 | mcp, httpx, BAA核心引擎 |
| 端口 | 8080（HTTP模式） |
| 超时 | 120秒（重构可能耗时较长） |
| 认证 | 支持 Bearer <REDACTED> |

---

## 3. OpenClaw Skill 方案

### 3.1 Skill目录结构

```
baa-blueprint-skill/
├── SKILL.md                          # Skill 说明文档
├── scripts/
│   ├── deconstruct.py                # 调用BAA REST API进行解构
│   ├── reconstruct.py                # 调用BAA REST API进行重构
│   ├── baa_client.py                 # BAA API 客户端封装
│   └── config.py                     # 配置（API Base URL, API Key）
└── README.md
```

### 3.2 SKILL.md

```markdown
---
name: baa-blueprint
description: BAA 蓝图重构能力，包含图纸解构和 BIM 模型生成
version: 1.0.0
---

# BAA 蓝图重构 Skill

## 使用场景
当用户请求图纸解构、BIM 模型生成、蓝图重构时使用本 Skill。

## 前置条件
- 配置 `scripts/config.py` 中的 `BAA_API_BASE` 和 `BAA_API_KEY`
- 确保 BAA 服务已启动

## 工具1：图纸解构（免费）

解析工程图纸，识别墙、柱、梁、板等构件信息。

```bash
python scripts/deconstruct.py <file_path>
```

参数：
- `file_path`：图纸文件路径（支持 dxf/dwg/pdf/jpg/png）

输出：JSON格式的构件列表（elements）+ file_id

## 工具2：BIM 重构（需授权验证）

基于解构结果生成 BIM 模型文件。

```bash
python scripts/reconstruct.py <file_id> <auth_token> [elements_json] [options_json]
```

参数：
- `file_id`：解构接口返回的 file_id（必填）
- `auth_token`：授权代收代付点生成的支付授权令牌（必填）
- `elements_json`：构件列表JSON（可选）
- `options_json`：重构参数JSON（可选，如 {"lod": 300, "format": "ifc"}）

## 授权说明

BAA 不处理定价和收款。BIM 重构服务需要有效的 auth_token。
auth_token 由授权代收代付点（如 EMA2）在用户支付完成后生成并传递。

auth_token 格式：JWT（Header.Payload.Signature）
- Payload 包含：order_id, service_type, expires_at
- 签名算法：HMAC-SHA256

## 配置

在 `scripts/config.py` 中配置：

```python
BAA_API_BASE = "https://baa-service.example.com"  # BAA 服务地址
BAA_API_KEY = "your-api-key-here"                  # API 密钥
```

## 示例

```bash
# 解构图纸
python scripts/deconstruct.py /path/to/drawing.dxf

# 重构 BIM 模型
python scripts/reconstruct.py "baa-file-abc123" "eyJhbGciOiJIUzI1NiJ9..."
```

## 错误处理

- 401：API Key 无效，检查 config.py 中的 BAA_API_KEY
- 402：授权验证失败，检查 auth_token 是否有效
- 403：授权已过期，请重新获取 auth_token
- 500：服务端错误，联系 BAA 团队
```

### 3.3 baa_client.py（BAA API客户端封装）

```python
# scripts/baa_client.py
"""BAA API 客户端封装"""

import httpx
import json
import os
from config import BAA_API_BASE, BAA_API_KEY

class BAAClient:
    """BAA API 客户端"""
    
    def __init__(self, api_base: str = None, api_key: str = None):
        self.api_base = api_base or BAA_API_BASE
        self.api_key = api_key or BAA_API_KEY
        self.client = httpx.AsyncClient(
            base_url=self.api_base,
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
    
    async def deconstruct(self, file_path: str) -> dict:
        """图纸解构"""
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, self._detect_mime(file_path))}
            response = await self.client.post("/deconstruct", files=files)
            response.raise_for_status()
            return response.json()
    
    async def reconstruct(
        self,
        file_id: str,
        auth_token: str,
        elements: list = None,
        options: dict = None
    ) -> dict:
        """BIM 重构"""
        payload = {
            "file_id": file_id,
            "auth_token": auth_token,
        }
        if elements:
            payload["elements"] = elements
        if options:
            payload["options"] = options
        
        response = await self.client.post("/reconstruct", json=payload)
        response.raise_for_status()
        return response.json()
    
    async def get_order(self, order_id: str) -> dict:
        """查询订单状态"""
        response = await self.client.get(f"/order/{order_id}")
        response.raise_for_status()
        return response.json()
    
    def _detect_mime(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            ".dxf": "application/dxf",
            ".dwg": "application/dwg",
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
        }
        return mime_map.get(ext, "application/octet-stream")
```

### 3.4 deconstruct.py 和 reconstruct.py

```python
# scripts/deconstruct.py
"""BAA 图纸解构（命令行工具）"""
import asyncio
import sys
import json
from baa_client import BAAClient

async def main():
    if len(sys.argv) < 2:
        print("用法: python deconstruct.py <file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    client = BAAClient()
    result = await client.deconstruct(file_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
```

```python
# scripts/reconstruct.py
"""BAA BIM 重构（命令行工具）"""
import asyncio
import sys
import json
from baa_client import BAAClient

async def main():
    if len(sys.argv) < 3:
        print("用法: python reconstruct.py <file_id> <auth_token> [elements_json] [options_json]")
        sys.exit(1)
    
    file_id = sys.argv[1]
    auth_token = sys.argv[2]
    elements = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    options = json.loads(sys.argv[4]) if len(sys.argv) > 4 else None
    
    client = BAAClient()
    result = await client.reconstruct(file_id, auth_token, elements, options)
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
```

### 3.5 config.py

```python
# scripts/config.py
"""BAA API 配置"""

import os

# BAA 服务地址
BAA_API_BASE = os.getenv("BAA_API_BASE", "https://baa-service.example.com")

# BAA API 密钥
BAA_API_KEY = os.getenv("BAA_API_KEY", "your-api-key-here")
```

### 3.6 EMA2侧安装方式

```bash
# 方式A：复制到 EMA2 的 skills 目录
cp -r baa-blueprint-skill /path/to/EMA2/skills/

# 方式B：通过 OpenClaw skill_workshop 安装
openclaw skill_workshop apply baa-blueprint
```

---

## 4. 三种接入方式选择指南

| 判断条件 | 推荐方式 | 理由 |
|---------|---------|------|
| EMA2有OpenClaw环境 | **MCP** | 自动发现工具，标准化调用 |
| EMA2无OpenClaw但有HTTP调用能力 | **REST API** | 最简单，零架构改动 |
| EMA2有OpenClaw但需要灵活编排 | **Skill** | 可包含完整业务逻辑 |
| 不确定 | **REST API + MCP** | 两种都提供，EMA2自行选择 |

**V1.0交付建议：** 先提供REST API（EMA2侧零改动），后续根据EMA2需要补充MCP和Skill。

---

## 5. 交付物清单

| 交付物 | 格式 | 说明 | 工作量 |
|--------|------|------|:------:|
| `baa_mcp_server.py` | Python | MCP Server 完整实现 | 2天 |
| `baa-blueprint-skill/` | 目录 | Skill 包（SKILL.md + scripts） | 1天 |
| `baa_mcp_docs.md` | Markdown | MCP接入文档 | 0.5天 |
| `baa_skill_docs.md` | Markdown | Skill安装和使用文档 | 0.5天 |

---

*编制：司军（AI业务助理）*
*日期：2026-06-20（终稿定稿）*
*依据：EMA2 API接口需求文档 v3.0 第5章*
*V1.0：REST API（已实现）*
*V2.0：MCP + Skill（设计先行，待实现）*