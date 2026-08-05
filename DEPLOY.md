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
## Kubernetes 生产部署（P63）

> 文件: `k8s/baa-deployment.yaml`

### 架构
```
Ingress(NGINX) → Service(ClusterIP:80) → 3×Deployment → PVC(/app/data)
                                ↕
                         HPA (2~10 副本)
```

### 前置要求
- Kubernetes 1.26+，含 Ingress NGINX Controller
- PVC 可用（本地/Cloud/EBS/RBD 等）

### 部署步骤

```bash
# 1. 创建命名空间
kubectl create ns baa

# 2. 构建 + 推送镜像
docker build -t baa:latest .
docker tag baa:latest registry.example.com/baa:latest
docker push registry.example.com/baa:latest

# 3. 更新镜像名（编辑 k8s/baa-deployment.yaml 中的 image 字段）

# 4. 应用配置
kubectl apply -f k8s/baa-deployment.yaml

# 5. 验证
kubectl get pods -n baa        # READY 3/3
kubectl get svc -n baa         # ClusterIP
kubectl get hpa -n baa         # TARGETS: CPU 0%/70%, MEM 0%/80%
kubectl get ingress -n baa     # baa.example.com
```

### HPA 策略
| 指标 | 阈值 | 说明 |
|------|------|------|
| CPU | 70% | 批量审查触发扩缩 |
| 内存 | 80% | OOM 保护 |
| min/max | 2~10 | 成本 vs 弹性平衡 |
| scaleUp window | 60s | 快速响应流量峰值 |
| scaleDown window | 300s | 避免频繁缩容 |

### 关键配置说明
- **共享数据**: 使用 PVC `baa-data-pvc` 挂载 `/app/data`（文件上传/密钥/审查历史）
  - 多副本场景建议使用**分布式存储**（NFS/Ceph/EBS CSI），避免有状态冲突
- **Ingress SSE 支持**: 启用 `proxy-http-version: 1.1` + Upgrade header，保证批量审查 SSE 进度推送正常工作
- **请求体上限**: `proxy-body-size: 50m`，适应大图纸上传
- **超时**: `proxy-read/send-timeout: 300s`，适应批量审查长任务

### 弹性伸缩触发示例
```bash
# 压测触发 HPA
for i in {1..20}; do
  curl -s -X POST http://baa.example.com/review \
    -H "Authorization: Bearer baa_prod_2026" \
    -F "file=@test.dxf" &
done
wait

kubectl get hpa -n baa -w  # 观察副本数上升
```
