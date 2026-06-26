# BAA 部署指南

## 快速启动（Docker 推荐）

### 前置条件
- Docker 24+ 和 Docker Compose v2+

### 1. 克隆并配置
```bash
git clone https://github.com/koros2018/BAA.git
cd BAA
cp .env.example .env
# 编辑 .env，至少设置 BAA_API_KEY（生产环境必填）
```

### 2. 构建并启动
```bash
docker compose up -d
# 查看日志
docker compose logs -f
```

### 3. 访问
- 前端 UI: http://localhost:8000/
- 健康检查: http://localhost:8000/health
- API 文档: http://localhost:8000/docs

### 4. 停止
```bash
docker compose down
```

## 配置说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| BAA_PORT | 8000 | 服务端口 |
| BAA_WORKERS | 4 | Worker 进程数 |
| BAA_API_KEY | (空) | 管理密钥，生产环境必须设置 |
| BAA_DATA_DIR | /app/data | 数据持久化目录 |
| BAA_KEY_TTL_DAYS | 90 | API 密钥有效期 |
| BAA_KEY_RATE_LIMIT | 60 | 每分钟最大请求数 |

## 卷挂载

```yaml
volumes:
  - baa_data:/app/data          # 持久化数据卷
  # - ./data/models:/app/data/models   # 挂载本地模型
  # - ./data/specs:/app/data/specs     # 挂载规范库
```

## 生产建议

1. **设置 BAA_API_KEY**: 生产环境必须设置管理密钥
2. **调整 workers**: CPU 密集型场景建议 workers=CPU核数
3. **配置反向代理**: 推荐 Nginx 前置代理，添加 SSL 和限流
4. **日志轮转**: Docker 日志已配置 10MB 轮转
5. **数据备份**: baa_data 卷定期备份

## 非 Docker 部署

### 开发模式
```bash
pip install -r requirements.txt
python src/api/baa_api.py
```

### 生产模式（直接部署）
```bash
pip install -r requirements.txt gunicorn uvicorn
gunicorn src.api.baa_api:app -k uvicorn.workers.UvicornWorker \
  -w 4 --bind 0.0.0.0:8000 --timeout 120 \
  --max-requests 10000 --preload
```