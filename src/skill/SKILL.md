---
name: baa-blueprint
description: BAA 蓝图重构能力，包含图纸解构、合规审查和 BIM 模型生成
version: 1.2.0
---

# BAA 蓝图重构 Skill

## 使用场景
当用户请求图纸解构、BIM 模型生成、蓝图重构、图纸合规审查时使用本 Skill。

## 前置条件
- BAA 服务已启动（默认 `http://localhost:8000`）
- 可通过 `scripts/config.py` 配置 API 地址和密钥

## 工具1：图纸解构（免费）

解析工程图纸，识别墙、柱、梁、板等构件信息。

```bash
python scripts/deconstruct.py <file_path> [building_type]
```

参数：
- `file_path`：图纸文件路径（支持 dxf/dwg）
- `building_type`：建筑类型，`civil`（民用）或 `industrial`（工业），默认 `civil`

输出：JSON 格式的构件列表（elements）+ file_id

## 工具2：图纸合规审查（免费）

基于 GB50016 规范检查图纸违规项。

```bash
python scripts/review.py <file_path> [building_type]
```

参数：
- `file_path`：图纸文件路径（支持 dxf/dwg）
- `building_type`：建筑类型，默认 `civil`

输出：违规详情 + 按条款汇总

## 工具3：BIM 重构（需授权验证）

基于解构结果生成 BIM 模型文件。

```bash
python scripts/reconstruct.py <file_id> <auth_token> [elements_json] [options_json]
```

参数：
- `file_id`：解构接口返回的 file_id（必填）
- `auth_token`：授权代收代付点生成的支付授权令牌（必填）
- `elements_json`：构件列表 JSON（可选）
- `options_json`：重构参数 JSON（可选，如 `{"lod": 300, "format": "ifc"}`）

## 授权说明

BAA 不处理定价和收款。BIM 重构服务需要有效的 auth_token。
auth_token 由授权代收代付点（如 EMA2）在用户支付完成后生成并传递。

auth_token 格式：JWT（Header.Payload.Signature）
- Payload 包含：order_id, service_type, expires_at
- 签名算法：HMAC-SHA256

## 配置

在 `scripts/config.py` 中配置：

```python
BAA_API_BASE = "http://localhost:8000"    # BAA 服务地址
BAA_API_KEY = ""                           # API 密钥（可选）
```

也可通过环境变量配置：
- `BAA_API_BASE`：服务地址
- `BAA_API_KEY`：API 密钥
- `BAA_DEFAULT_BUILDING_TYPE`：默认建筑类型

## 示例

```bash
# 解构图纸（民用）
python scripts/deconstruct.py /path/to/drawing.dxf

# 解构图纸（工业建筑）
python scripts/deconstruct.py /path/to/drawing.dxf industrial

# 合规审查
python scripts/review.py /path/to/drawing.dxf

# 重构 BIM 模型
python scripts/reconstruct.py "baa-file-abc123" "eyJhbGciOiJIUzI1NiJ9..."
```

## 错误处理

| 状态码 | 含义 | 处理方式 |
|--------|------|---------|
| 401 | API Key 无效 | 检查 config.py 中的 BAA_API_KEY |
| 402 | 授权验证失败 | 检查 auth_token 是否有效 |
| 403 | 授权已过期 | 请重新获取 auth_token |
| 500 | 服务端错误 | 联系 BAA 团队 |

## 文件索引

```
src/skill/
├── SKILL.md                   ← 本文件
└── scripts/
    ├── config.py              # API 配置
    ├── baa_client.py          # BAA API 客户端封装
    ├── deconstruct.py         # 图纸解构（命令行）
    ├── reconstruct.py         # BIM 重构（命令行）
    └── review.py              # 图纸合规审查（命令行）
```
