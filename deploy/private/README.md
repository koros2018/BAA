# BAA 私有部署包

> **版本**：v2.5.80-stable  
> **适用场景**：企业内部私有化部署（Linux / macOS / WSL2）  
> **前置条件**：Docker 24+、Docker Compose v2+

---

## 1. 快速开始（10 分钟内完成）

```bash
# ① 克隆仓库
git clone <repo-url> && cd BAA

# ② 生成安全密钥（首次部署）
./deploy/private/deploy.sh init

# ③ 一键启动
./deploy/private/deploy.sh up

# ④ 查看日志 / 验证健康
curl http://localhost:8000/health
docker compose logs -f baa
```

### 验证清单

| 端点 | 预期 |
|------|------|
| `GET /health` | 200，subsystems 含 postgres (ok) |
| `GET /metrics` | 200，prometheus 格式 |
| `GET /api/v1/functions` | 401（无密钥时）或 200（有密钥时） |
| `GET /api/v1/admin/audit/logs` | 401（需 admin scope） |

---

## 2. 目录结构

```
BAA/
├── Dockerfile                      # 多阶段构建（python:3.12-slim）
├── docker-compose.yml              # PostgreSQL + BAA 单栈
├── docker-entrypoint.sh            # alembic upgrade head → gunicorn
├── .env.example                    # 本地开发配置模板
├── .env.production.example        # 生产配置模板（T-C5 安全基线）
├── deploy/
│   └── private/
│       ├── README.md               # 本文件
│       ├── deploy.sh               # Linux/macOS 一键脚本
│       └── deploy.ps1              # Windows/WSL2 一键脚本
└── src/
    ├── api/baa_api.py              # FastAPI 主应用
    ├── baa_engine/                 # 引擎核心
    └── frontend/                   # 前端静态资源
```

---

## 3. 配置说明

### 3.1 必填环境变量

将 `.env.production.example` 复制为 `.env`，修改以下字段：

```bash
BAA_API_KEY=<强随机值>                    # 管理密钥，至少 32 字符
POSTGRES_PASSWORD=<强随机值>              # PostgreSQL 密码
```

生成强随机密钥：
```bash
# Linux/macOS
python -c "import secrets; print(secrets.token_urlsafe(48))"

# Windows PowerShell
[System.Web.Security.Membership]::GeneratePassword(48, 12)
```

### 3.2 可选环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BAA_PORT` | 8000 | HTTP 服务端口 |
| `BAA_WORKERS` | 4 | Gunicorn worker 数（CPU 核数 ≈ 2×4 推荐） |
| `BAA_PDF_ISOLATION` | 1 | AGPL 进程隔离（生产必须开启） |
| `BAA_ALLOW_ANONYMOUS` | 0 | **生产必须为 0** |
| `BAA_LOG_FORMAT` | json | 结构化日志（Loki/ELK 兼容） |
| `BAA_DATABASE_URL` | — | 自动生成，无需手动设置 |

---

## 4. 部署命令参考

### 启动服务
```bash
# 标准启动（后台）
docker compose up -d

# 前台调试（带日志）
docker compose up

# 指定配置文件
BAA_ENV=production docker compose --env-file .env.production up -d
```

### 数据持久化
PostgreSQL 数据卷：`pg_data`（Docker volume，重启不丢）  
BAA 数据目录：`baa_data`（上传文件、日志、规范库）

查看数据卷：
```bash
docker volume ls | grep baa
docker volume inspect baa_pg_data
```

### 更新镜像
```bash
docker compose pull && docker compose up -d
# 或强制重建
docker compose up -d --build
```

### 完全重置（⚠️ 会清空数据）
```bash
docker compose down -v    # -v 删除数据卷
docker compose up -d
```

---

## 5. 生产加固建议

### 5.1 反向代理（Nginx / Caddy）

BAA 服务在 8000 端口运行，**生产环境必须经反向代理暴露**：

```nginx
# Nginx 示例（/etc/nginx/sites-available/baa）
server {
    listen 443 ssl;
    server_name baa.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/baa.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/baa.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }
}
```

### 5.2 多副本扩展

```bash
# 水平扩展至 3 副本（共享同一 PG）
docker compose up -d --scale baa=3
# 配合 nginx upstream 轮询 8000-8002
```

### 5.3 监控

```bash
# Prometheus scrape（默认 :8000/metrics）
# Alertmanager 规则见 k8s/prometheus-rules.yaml（可裁剪用于 docker）
```

---

## 6. 故障排查

### 容器启动后 `/health` 返回 500

```bash
# 查看 alembic 迁移日志
docker compose logs baa | grep -i "alembic\|error\|traceback"

# 检查 PG 连接
docker compose exec postgres psql -U baa -d baa -c "SELECT 1"
```

### 审计日志 API 返回 401

```bash
# 检查 BAA_API_KEY 是否正确注入
docker compose exec baa env | grep BAA_API_KEY

# 验证 key 权限（admin scope 可访问 /api/v1/admin/audit/logs）
curl -H "Authorization: Bearer $BAA_API_KEY" http://localhost:8000/api/v1/admin/audit/logs
```

### 镜像构建失败

```bash
# 清理 BuildKit 缓存后重试
docker builder prune -af
docker compose build --no-cache
```

---

## 7. 合规声明

- **AGPL 隔离**：PyMuPDF（AGPL）仅在子进程中运行，主进程不导入。`BAA_PDF_ISOLATION=1`（默认）
- **YOLOv8 禁用**：`VISION_ENABLED` 默认 false，enhancement.py 返回空列表，`pip install baa` 不安装 ultralytics
- **许可证**：BAA 核心代码 MIT；如需分发 PyMuPDF/YOLOv8，请使用 `pip install baa[full]`

---

*文档版本：2026-10-27 · 对应 Roadmap v5 E3-T1 验收*
