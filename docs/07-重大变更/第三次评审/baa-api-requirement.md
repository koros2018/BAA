# BAA 商业化 - API 接口需求文档

> 版本：v3.0 | 日期：2026-06-16 | 作者：GDP影子（EMA2 技术侧）

---

## 1. 背景

EMA2 是一个工程管理智能体平台，BAA 蓝图重构是其唯一付费功能。当前代码中 BAA 模块全部是 **mock 模式**，需要接入 BAA 团队的真实 API。

### 当前定价策略

| 方案 | 单价 | 说明 |
|------|------|------|
| 单张重构 | 9.9 元/张 | 1 张图纸 |
| 批量 10 张 | 7.9 元/张 | 批量优惠 |
| 批量 50 张 | 5.9 元/张 | 大批量优惠 |
| 月度无限 | 29.0 元/月 | 不限次数 |

### 分成比例

- BAA 团队：70%
- EMA2 平台：30%

### 免费额度

- 每月前 3 次 BAA 重构免费（所有用户）

---

## 2. 现有代码对接点

EMA2 后端已有完整的 mock 实现，BAA 团队只需提供以下接口，EMA2 侧零改动即可对接。

### 2.1 当前 API 调用链

前端 -> EMA2 API (7188) -> BAA Client (baa_client.py) -> BAA 服务

### 2.2 BAA Client 代码位置

`src/services/baa_client.py` 两个核心函数：

    async def baa_deconstruct(file_path: str) -> dict:
        # BAA 解构（免费）- 解析图纸，提取构件信息

    async def baa_reconstruct(file_path: str, elements: list) -> dict:
        # BAA 重构（收费）- 生成 BIM 模型

### 2.3 配置项（config.py）

    BAASERVICE = {
        "api_base": os.getenv("BAA_API_BASE", ""),  # 空 = mock 模式
        "api_key": os.getenv("BAA_API_KEY", ""),
    }

只需设置环境变量 `BAA_API_BASE` 和 `BAA_API_KEY`，EMA2 自动切换为真实模式。

---

## 3. BAA 团队需提供的接口

### 接口 1：图纸解构（免费）

用途：用户上传图纸后，BAA 自动识别图纸中的构件信息（墙、柱、梁、板等），返回结构化数据。此接口免费，用于展示预览。

    POST {BAA_API_BASE}/deconstruct
    Authorization: Bearer {api_key}
    Content-Type: multipart/form-data

    Request:
      file: <图纸文件二进制>  (支持 PDF / DWG / DXF / JPG / PNG)

    Response (200):
    {
      "status": "success",
      "elements": [
        {"type": "wall", "count": 12, "total_length": 45.6},
        {"type": "column", "count": 8, "total_volume": 15.2},
        {"type": "beam", "count": 16, "total_length": 62.4},
        {"type": "slab", "count": 4, "total_area": 320.0}
      ],
      "confidence": 0.92,
      "file_id": "abc123"
    }

说明：
- 这是免费接口，不限次数
- 返回的 file_id 用于后续重构接口关联
- elements 中的 type 字段建议取值：wall, column, beam, slab, door, window, stair, elevator 等
- confidence 是识别置信度 0-1

---

### 接口 2：BIM 重构（收费）

用途：基于解构结果（或原始图纸），生成完整的 BIM 模型文件。这是收费接口。

    POST {BAA_API_BASE}/reconstruct
    Authorization: Bearer {api_key}
    Content-Type: application/json

    Request:
    {
      "file_id": "abc123",
      "elements": [
        {"type": "wall", "count": 12, "total_length": 45.6}
      ],
      "options": {
        "lod": 300,
        "format": "ifc",
        "include_reinforcement": false
      }
    }

    Response (200):
    {
      "status": "success",
      "order_id": "baa-xxxxx",
      "model_url": "https://baa-service.com/models/xxx.ifc",
      "elements_count": 40,
      "processing_time_ms": 15000,
      "file_size_mb": 2.5
    }

    Response (202):
    {
      "status": "processing",
      "order_id": "baa-xxxxx",
      "message": "正在处理中，请稍后查询",
      "estimated_time_ms": 30000
    }

说明：
- 这是收费接口，EMA2 侧已有订单系统
- 如果重构耗时较长，返回 202 + order_id，EMA2 侧可轮询查询进度
- model_url 是生成的 BIM 模型文件下载地址
- options 参数可选，有默认值

---

### 接口 3（可选）：订单状态查询

用途：查询重构任务的处理状态（如果重构接口返回 202）。

    GET {BAA_API_BASE}/order/{order_id}
    Authorization: Bearer {api_key}

    Response (200):
    {
      "order_id": "baa-xxxxx",
      "status": "completed",
      "model_url": "https://baa-service.com/models/xxx.ifc",
      "progress": 100
    }

    Response (200) - 进行中:
    {
      "order_id": "baa-xxxxx",
      "status": "processing",
      "progress": 65
    }

---

## 4. 支付流程（EMA2 侧已有，BAA 团队无需关心）

EMA2 侧的支付流程已经设计完成：

    1. 用户选择方案（单张/批量/月卡）
    2. EMA2 创建订单（POST /api/v1/baa/order）-> 返回订单信息
    3. 前端展示微信支付二维码（当前是静态图片 mock）
    4. 用户扫码支付
    5. EMA2 确认支付（POST /api/v1/subscription/baa/pay）
    6. 调用 BAA 重构接口

如果 BAA 团队有自己的支付系统，EMA2 侧可以调整为：
- EMA2 创建订单后，返回 BAA 的支付链接
- 用户在 BAA 侧完成支付
- BAA 回调 EMA2 确认

如果走 EMA2 侧支付，BAA 团队只需提供上述 2-3 个 API 接口，支付由 EMA2 处理。

---

## 5. 接入方式详细方案

### 方案 A：REST API（推荐）

适用场景：BAA 团队有现成的 HTTP 服务（Flask/FastAPI/Spring Boot 等），或愿意快速搭建一个。

对接步骤：
1. BAA 团队提供 API Base URL 和 API Key
2. EMA2 设置环境变量：
   export BAA_API_BASE=https://baa-service.example.com
   export BAA_API_KEY=sk-baa-xxxxx
3. EMA2 重启，自动切换为真实模式
4. 测试验证

EMA2 侧代码零改动。当前 baa_client.py 已经是标准 httpx 异步调用，配置生效后自动走真实 API。

BAA 团队需要做的：
- 提供 3 个 HTTP 接口（见第 3 节）
- 支持 multipart/form-data 文件上传（解构接口）
- 支持 Bearer <REDACTED> 认证
- 返回 JSON 格式数据

优点：简单直接，EMA2 侧零架构改动，BAA 团队技术栈不限
缺点：需要 BAA 团队有 HTTP 服务能力

---

### 方案 B：MCP 接口（Model Context Protocol）

适用场景：BAA 团队使用 OpenClaw 生态，或愿意将 BAA 能力封装为 MCP server。

什么是 MCP？
MCP 是一个标准化协议，让 AI agent 能发现和调用外部工具。OpenClaw 原生支持 MCP client，可以连接任何 MCP server。

对接步骤：

1. BAA 团队将 BAA 能力封装为 MCP server，暴露 2 个工具：
   - baa_deconstruct - 图纸解构
   - baa_reconstruct - BIM 重构

2. EMA2 侧通过 OpenClaw 的 MCP client 注册 BAA server：

   # 如果 BAA 是远程 HTTP MCP server
   openclaw mcp add baa \
     --url https://baa-service.example.com/mcp \
     --transport streamable-http \
     --header "Authorization: Bearer sk-baa-xxxxx" \
     --timeout 120

   # 如果 BAA 是本地 stdio MCP server
   openclaw mcp add baa \
     --command python \
     --arg /path/to/baa_mcp_server.py \
     --timeout 120

3. EMA2 agent 运行时自动发现 BAA 工具，在需要时调用

MCP Server 需要暴露的工具定义：

    {
      "tools": [
        {
          "name": "baa_deconstruct",
          "description": "解构工程图纸，识别墙、柱、梁、板等构件",
          "inputSchema": {
            "type": "object",
            "properties": {
              "file_path": {"type": "string", "description": "图纸文件路径"}
            },
            "required": ["file_path"]
          }
        },
        {
          "name": "baa_reconstruct",
          "description": "基于构件信息生成 BIM 模型（收费）",
          "inputSchema": {
            "type": "object",
            "properties": {
              "file_id": {"type": "string", "description": "解构接口返回的 file_id"},
              "elements": {"type": "array", "description": "构件列表（可选）"},
              "options": {"type": "object", "description": "重构参数"}
            },
            "required": ["file_id"]
          }
        }
      ]
    }

MCP 协议细节：
- 支持 stdio 和 streamable-http 两种传输方式
- 工具发现自动，agent 运行时动态获取可用工具列表
- 支持 OAuth 认证和 Bearer <REDACTED>
- 支持超时配置和并发调用
- 支持工具过滤（include/exclude）

优点：标准化接口发现，BAA 团队只需关注工具逻辑，认证/重试/限流由 MCP 协议处理
缺点：BAA 团队需要了解 MCP 协议，需要 OpenClaw 生态支持

---

### 方案 C：OpenClaw Skill

适用场景：BAA 团队使用 OpenClaw，或愿意将 BAA 能力封装为可复用的 OpenClaw Skill。

什么是 OpenClaw Skill？
Skill 是 OpenClaw 的可复用能力包，包含 SKILL.md（使用说明）和可选的脚本/模板。Agent 读取 SKILL.md 后按指引执行操作。

对接步骤：

1. BAA 团队创建 Skill 目录结构：

    baa-blueprint/
    +-- SKILL.md              # Skill 说明文档
    +-- scripts/
    |   +-- deconstruct.py   # 解构脚本（调用 BAA API）
    |   +-- reconstruct.py   # 重构脚本（调用 BAA API）
    +-- README.md

2. SKILL.md 内容示例：

    ---
    name: baa-blueprint
    description: BAA 蓝图重构能力，包含图纸解构和 BIM 模型生成
    ---

    # BAA 蓝图重构

    ## 使用场景
    当用户请求蓝图重构、BIM 模型生成、图纸解构时使用本 Skill。

    ## 解构（免费）
    python scripts/deconstruct.py <file_path>

    ## 重构（收费）
    python scripts/reconstruct.py <file_id> [elements_json]

    ## 定价
    - 单张：9.9 元
    - 批量 10 张：7.9 元/张
    - 月度无限：29 元

3. EMA2 侧安装 Skill：
   cp -r baa-blueprint /mnt/d/OpenclawData/workspace/Projects/EMA2/skills/

4. EMA2 agent 在对话中自动识别 BAA 相关意图，读取 SKILL.md 后按指引调用脚本

Skill 的高级用法：
- 可以包含参数模板（Jinja2 格式），动态生成命令
- 可以包含多步骤工作流，agent 按顺序执行
- 可以包含条件判断，根据不同场景选择不同脚本
- 可以包含错误处理和重试逻辑

优点：最灵活，可以包含完整的业务逻辑和参数说明，非技术人员也能维护
缺点：需要 BAA 团队了解 OpenClaw Skill 格式，执行效率略低于 MCP

---

## 6. 三种方案对比

| 维度 | REST API | MCP 接口 | OpenClaw Skill |
|------|----------|----------|----------------|
| 开发成本 | 低（标准 HTTP） | 中（需了解 MCP） | 中（需了解 Skill） |
| EMA2 改动 | 零 | 需注册 MCP server | 需安装 Skill |
| BAA 技术栈 | 不限 | 需 MCP server | 需 Python/Shell |
| 接口发现 | 手动文档 | 自动 | 自动（SKILL.md） |
| 认证方式 | Bearer <REDACTED> | MCP 协议层 | 脚本内处理 |
| 可维护性 | 中 | 高 | 高 |
| 推荐场景 | BAA 有现成 HTTP 服务 | BAA 在 OpenClaw 生态 | BAA 需要灵活编排 |

建议：如果 BAA 团队有现成 HTTP 服务 -> REST API；如果想标准化 -> MCP；如果想快速验证 -> Skill。

---

## 7. 技术对接清单（BAA 团队需提供）

| # | 项目 | 说明 | 优先级 |
|---|------|------|--------|
| 1 | API Base URL | 服务地址 | P0 |
| 2 | API Key | 认证密钥 | P0 |
| 3 | /deconstruct 接口 | 图纸解构（免费） | P0 |
| 4 | /reconstruct 接口 | BIM 重构（收费） | P0 |
| 5 | /order/{id} 接口 | 订单状态查询（可选） | P1 |
| 6 | API 文档 | 接口说明文档 | P0 |
| 7 | 测试账号 | 用于 EMA2 集成测试 | P1 |
| 8 | 回调地址（可选） | 支付完成后的回调 URL | P2 |

---

## 8. EMA2 侧对接人

- 技术对接：GDP影子（刚哥的 AI 助手）
- 测试环境：http://127.0.0.1:7188（本地开发）
- 生产环境：待部署
- 代码位置：/mnt/d/OpenClawData/workspace/Projects/EMA2/src/services/baa_client.py

---

## 9. 附录：当前 Mock 数据

以下是当前 mock 模式返回的数据格式，供 BAA 团队参考：

Mock 解构结果：
    {
      "status": "success",
      "elements": [
        {"type": "wall", "count": 12, "total_length": 45.6},
        {"type": "column", "count": 8, "total_volume": 15.2},
        {"type": "beam", "count": 16, "total_length": 62.4},
        {"type": "slab", "count": 4, "total_area": 320.0}
      ],
      "confidence": 0.92,
      "mock": true
    }

Mock 重构结果：
    {
      "status": "success",
      "model_url": "https://mock.baa.model/abc123",
      "elements_count": 40,
      "mock": true
    }

---


---

## 10. 最终决策：三种方案全选

经与刚哥确认，EMA2 侧将 **同时支持三种接入方式**，按优先级切换：

### 优先级链

1. **MCP 接口**（优先尝试）
   - 如果 BAA 团队提供 MCP server，EMA2 通过 OpenClaw MCP client 连接
   - 自动发现工具，标准化调用

2. **REST API**（次选）
   - 如果 BAA 团队提供 HTTP API，EMA2 通过 httpx 调用
   - 配置 BAA_API_BASE + BAA_API_KEY 环境变量即可

3. **OpenClaw Skill**（兜底）
   - 如果 BAA 团队提供 Skill，EMA2 通过 skill_workshop 安装
   - Agent 读取 SKILL.md 后按指引执行

### 自动切换逻辑



### BAA 团队行动项

请 BAA 团队根据自身情况，提供以下任意一种（或多种）：

| 接入方式 | BAA 团队需要提供 | 对接人 |
|----------|-----------------|--------|
| MCP | MCP server 端点 URL + 认证方式 | EMA2 侧零改动 |
| REST API | API Base URL + API Key + 接口文档 | EMA2 侧零改动 |
| Skill | baa-blueprint/ 目录（SKILL.md + scripts/） | EMA2 侧安装 Skill |

越多越好，EMA2 侧自动选择最优方式。

---

_文档版本 v3.0 - 2026-06-16_
_如有疑问请通过刚哥联系 GDP影子_
