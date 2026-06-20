# BAA 授权对接规范文档

> **版本：** v1.0 | **更新时间：** 2026-06-20  
> **适用对象：** EMA2团队 / 授权代收代付点技术对接  
> **核心原则：** BAA不处理定价/收款，仅验证授权代收代付点传输的支付信息后提供服务

---

## 1. 对接概述

### 1.1 流程总览

```
用户 → EMA2前端 → EMA2后端(7188) → BAA Client → 支付确认
                                                    ↓
                                             授权代收代付点
                                                    ↓
                                           auth_token生成
                                                    ↓
                                              BAA API 服务
                                                    ↓
                                            BIM模型下载
```

### 1.2 角色说明

| 角色 | 责任 | 系统 |
|------|------|------|
| **用户** | 上传图纸、查看审查结果、确认订单 | EMA2前端 |
| **EMA2平台** | 提供前端UI、转发请求 | EMA2后端（7188端口） |
| **BAA服务** | 图纸解析、合规审查、BIM重构 | BAA API（8000端口） |
| **授权代收代付点** | 处理支付、生成授权令牌 | 第三方支付平台 |

---

## 2. 对接准备

### 2.1 环境信息

| 项目 | 值 | 说明 |
|------|:---:|------|
| BAA API Base URL | `http://<baa-server>:8000` | 生产环境替换为实际域名 |
| API Key | 由BAA提供 | Bearer Token认证 |
| 共享密钥 | 由BAA提供 | HMAC-SHA256签名密钥 |
| 密钥轮换周期 | 90天 | 旧密钥48小时宽限期 |

### 2.2 环境变量配置

EMA2后端需配置以下环境变量：

```bash
# BAA服务地址
BAA_API_URL=http://localhost:8000
# API Key（BAA提供）
BAA_API_KEY=your-api-key-here
# 共享密钥（用于auth_token签名验证）
BAA_AUTH_SECRET=your-shared-secret-here
```

---

## 3. 授权令牌规范

### 3.1 令牌格式

auth_token为JWT格式（HMAC-SHA256签名），由三部分组成：

```
{header}.{payload}.{signature}
```

### 3.2 Header

```json
{
  "alg": "HS256",
  "typ": "JWT"
}
```

### 3.3 Payload

| 字段 | 类型 | 必填 | 说明 |
|------|:----:|:----:|------|
| `order_id` | string | 是 | EMA2侧订单ID |
| `service` | string | 是 | 服务类型：`reconstruct` |
| `issued_at` | string (ISO8601) | 是 | 令牌签发时间 |
| `expires_at` | string (ISO8601) | 是 | 令牌过期时间 |
| `quota.max_requests` | int | 是 | 最大请求次数（通常为1） |
| `quota.max_file_size_mb` | int | 是 | 允许处理的文件大小上限 |
| `client_id` | string | 是 | 客户端标识：`ema2-platform` |

### 3.4 Signature

```python
import hmac
import hashlib
import base64
import json

def generate_auth_token(payload: dict, secret: str) -> str:
    """生成auth_token"""
    header = {"alg": "HS256", "typ": "JWT"}
    
    def b64encode(data: dict) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(data, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
    
    header_b64 = b64encode(header)
    payload_b64 = b64encode(payload)
    signing_input = f"{header_b64}.{payload_b64}"
    
    sig = hmac.new(
        secret.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    
    return f"{header_b64}.{payload_b64}.{sig_b64}"
```

### 3.5 令牌示例

```
eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.
eyJvcmRlcl9pZCI6ICJlbWEyLW9yZGVyLTAwMSIsICJzZXJ2aWNlIjogInJlY29uc3RydWN0In0.
x1Y2Z3a4b5c6d7e8f9g0h1i2j3k4l5m6n7o8p9q0r1s2t3u4v5w6x7y8z9
```

---

## 4. 支付与授权流程

### 4.1 标准流程

```
1. 用户上传图纸 → BAA解析（免费）
2. 用户确认需要BIM重构 → EMA2引导用户支付
3. 支付完成 → 授权代收代付点生成auth_token
4. EMA2后端携带auth_token调用BAA /reconstruct
5. BAA验证auth_token（HMAC签名+有效期+配额）
6. 验证通过 → 执行BIM重构 → 返回模型下载链接
```

### 4.2 auth_token传递流程

```
授权代收代付点                  EMA2后端                  BAA API
     │                            │                        │
     │  1. 用户完成支付            │                        │
     │                            │                        │
     │  2. 生成auth_token ──────►  │                        │
     │                            │                        │
     │                            │  3. POST /reconstruct  │
     │                            │     {file_id,          │
     │                            │      auth_token,       │
     │                            │      order_id} ──────► │
     │                            │                        │
     │                            │                        │  4. 验证签名
     │                            │                        │  5. 验证有效期
     │                            │                        │  6. 执行重构
     │                            │                        │
     │                            │  7. 返回model_url ◄── │
     │                            │                        │
     │  8. 用户下载模型 ◄─────────│                        │
```

### 4.3 安全注意事项

1. **共享密钥保护**：BAA_AUTH_SECRET不得在前端暴露，仅后端存储
2. **令牌有效期**：建议设置为支付完成后的2-3小时内
3. **防重放**：每个auth_token仅能使用一次（`max_requests: 1`）
4. **文件绑定**：auth_token不绑定特定file_id，但BAA会验证file_id存在性
5. **传输加密**：生产环境必须使用HTTPS

---

## 5. BAA Client 配置（EMA2侧）

### 5.1 环境变量

```bash
# 必需
export BAA_API_URL="http://localhost:8000"
export BAA_API_KEY="your-api-key"
export BAA_AUTH_SECRET="your-shared-secret"

# 可选
export BAA_TIMEOUT_SECONDS=60
export BAA_MAX_RETRIES=3
```

### 5.2 调用示例（EMA2后端Python代码）

```python
import os
import requests
import json

BAA_API_URL = os.getenv("BAA_API_URL", "http://localhost:8000")
BAA_API_KEY = os.getenv("BAA_API_KEY", "")


def review_drawing(file_path: str) -> dict:
    """上传图纸并执行合规审查"""
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{BAA_API_URL}/review",
            files={"file": (os.path.basename(file_path), f, "application/dxf")},
            headers={"Authorization": f"Bearer {BAA_API_KEY}"},
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json()


def reconstruct_drawing(file_id: str, auth_token: str, order_id: str) -> dict:
    """执行BIM重构"""
    resp = requests.post(
        f"{BAA_API_URL}/reconstruct",
        json={
            "file_id": file_id,
            "auth_token": auth_token,
            "order_id": order_id,
        },
        headers={"Authorization": f"Bearer {BAA_API_KEY}"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def check_order(order_id: str) -> dict:
    """查询订单状态"""
    resp = requests.get(
        f"{BAA_API_URL}/order/{order_id}",
        headers={"Authorization": f"Bearer {BAA_API_KEY}"},
    )
    resp.raise_for_status()
    return resp.json()
```

### 5.3 EMA2 baa_client.py 集成适配

如果EMA2已有`baa_client.py`，调整以下配置即可：

```python
# baa_client.py 中
BAA_CONFIG = {
    "base_url": os.getenv("BAA_API_URL", "http://localhost:8000"),
    "api_key": os.getenv("BAA_API_KEY", ""),
    "timeout": 60,
}
```

EMA2侧代码零改动，仅配置环境变量。

---

## 6. 密钥管理

### 6.1 共享密钥轮换

| 操作 | 频率 | 说明 |
|------|:----:|------|
| 初始密钥分发 | 首次对接 | BAA提供初始共享密钥 |
| 常规轮换 | 每90天 | BAA生成新密钥，分发给授权代收代付点 |
| 宽限期 | 48小时 | 新旧密钥同时有效，供过渡使用 |
| 紧急轮换 | 按需 | 密钥泄露时立即执行 |

### 6.2 密钥存储

- BAA侧：环境变量 `BAA_AUTH_SECRET`
- 授权代收代付点侧：安全存储（如KMS/HSM）
- EMA2侧：不需要存储共享密钥（不参与签名）

### 6.3 密钥验证流程（BAA侧）

```python
def verify_auth_token(token: str, active_secrets: list) -> Optional[dict]:
    """用当前活跃的所有密钥尝试验证"""
    for secret in active_secrets:
        result = _verify_with_secret(token, secret)
        if result is not None:
            return result
    return None

# active_secrets: [新密钥, 旧密钥（48h宽限期）]
```

---

## 7. 测试环境

### 7.1 测试密钥

```bash
# 开发/测试环境
BAA_API_KEY=test-api-key
BAA_AUTH_SECRET=test-secret
```

### 7.2 测试流程

```bash
# 1. 健康检查
curl http://localhost:8000/health

# 2. 上传图纸（免费）
curl -X POST http://localhost:8000/deconstruct \
  -H "Authorization: Bearer test-api-key" \
  -F "file=@test.dxf"

# 3. 生成测试auth_token（Python）
python3 -c "
from src.api.baa_api import generate_auth_token
import datetime

token = generate_auth_token({
    'order_id': 'test-order-001',
    'service': 'reconstruct',
    'issued_at': datetime.datetime.utcnow().isoformat(),
    'expires_at': (datetime.datetime.utcnow() + datetime.timedelta(hours=2)).isoformat(),
    'quota': {'max_requests': 1, 'max_file_size_mb': 50},
    'client_id': 'ema2-platform',
})
print(token)
"

# 4. BIM重构（付费）
curl -X POST http://localhost:8000/reconstruct \
  -H "Authorization: Bearer test-api-key" \
  -H "Content-Type: application/json" \
  -d '{"file_id": "baa-file-xxx", "auth_token": "<generated-token>", "order_id": "test-order-001"}'
```

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|:----:|:----:|---------|
| v1.0 | 2026-06-20 | 初始版本 |