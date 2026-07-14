# BAA 部署指南

> 版本：v2.5.4-stable | 日期：2026-07-14

## 环境要求

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | ≥ 3.12 | 运行时 |
| Node.js | ≥ 20 | 静态文件服务（可选） |
| Git | ≥ 2.40 | 版本管理 |

## 一、开发环境部署

### 1.1 拉取代码

```bash
git clone <repo-url> Projects/BAA
cd Projects/BAA
git checkout v2.5.4-stable
```

### 1.2 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 1.3 启动服务

```bash
gunicorn -w 2 -k uvicorn.workers.UvicornWorker \
  -b 0.0.0.0:8000 \
  src.api.baa_api:app \
  --timeout 120 \
  --access-logfile data/logs/access.log \
  --error-logfile data/logs/error.log \
  --log-level info
```

### 1.4 访问

- 前端：http://localhost:8000
- API 文档（如启用）：http://localhost:8000/docs

## 二、生产部署

### 2.1 反向代理配置（Nginx）

```nginx
server {
    listen 80;
    server_name baa.yourdomain.com;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_read_timeout 300s;
    }
}
```

### 2.2 API Key 配置

环境变量 `BAA_API_KEY` 设置开发模式密钥：

```bash
export BAA_API_KEY="your-secret-key"
```

或从 `src/data/api_keys.json` 读取：

```json
{
  "development": {"token": "dev-token", "roles": ["admin"]},
  "production": {"token": "prod-token", "roles": ["user"]}
}
```

## 三、容器化部署（Dockerfile 待定）

> 当前 v2.5.4 暂未提供 Dockerfile，建议使用上面的 Python 环境直接部署。

## 四、数据库

- SQLite 数据库位于 `src/data/`，自动创建
- 无需额外配置数据库服务

## 五、静态文件

前端位于 `src/frontend/`，包含：

| 文件 | 用途 |
|------|------|
| `index.html` | 主页面（691 行模板） |
| `baa.css` | 样式（拆分后的 Tailwind 工具类） |
| `baa-core.js` | 核心功能（API 调用、认证） |
| `baa-review.js` | 审图页面 |
| `baa-admin.js` | 规范/图纸管理 + 协作 |
| `baa-analysis.js` | 结果分析 |
| `baa-initialize.js` | 页面初始化 |
| `baa-ext.js` | 反向重构 + 原子函数库 + 布局可视化 |

## 六、健康检查

```bash
# 检查服务是否存活
curl -f http://localhost:8000/ || echo "服务未响应"

# 检查 API 端点
curl -f http://localhost:8000/api/v1/functions | python3 -m json.tool
```

## 七、日志

| 日志 | 路径 |
|------|------|
| 访问日志 | `data/logs/access.log` |
| 错误日志 | `data/logs/error.log` |
| 训练日志 | `runs/train/baa_v4_training.log`（如启用 YOLO 训练） |

## 八、常见问题

**Q: 127.0.0.1 超时，0.0.0.0 正常？**
A: WSL2 环境下 127.0.0.1 可能不通，用 `0.0.0.0` 绑定，从宿主机访问用 WSL IP。

**Q: 数据库文件被锁定？**
A: SQLite 并发写入会导致锁。确保同一时间只有一个写操作，或者升级至 SQLite WAL 模式。

**Q: YOLO 模型未训练？**
A: 首次部署需训练 YOLO 模型（`runs/train/` 目录），或使用规则引擎兜底。
