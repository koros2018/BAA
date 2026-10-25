# =============================================================================
# BAA - Blueprint AI Agent 多阶段构建 Dockerfile
# =============================================================================

# ── 第一阶段：构建环境 ────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# 系统构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖清单和 YOLO 配置
COPY requirements.txt pyproject.toml ./

# 安装所有依赖到 /install
RUN pip install --user --no-cache-dir -r requirements.txt

# 预下载 YOLOv8n 权重（避免运行时首次下载慢）
RUN python3 -c "from ultralytics import YOLO; YOLO('yolov8n.pt', download=False)" 2>/dev/null || \
    python3 -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

# ── 第二阶段：运行环境 ────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="BAA - Blueprint AI Agent"
LABEL org.opencontainers.image.description="图纸合规智能体 - DXF/DWG 图纸 AI 审查系统"
LABEL org.opencontainers.image.version="2.5.80"
LABEL org.opencontainers.image.source="https://github.com/koros2018/BAA"

# 系统运行依赖（ezdwg/ezdxf 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libc6 \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制已安装的包
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

WORKDIR /app

# 复制项目代码（.dockerignore 已排除开发/测试/本地状态/密钥文件）
COPY . .

# 生产启动脚本（先迁移后服务）
RUN chmod +x docker-entrypoint.sh

# 创建数据目录（卷挂载点）
RUN mkdir -p /app/data/files /app/data/models /app/data/logs /app/data/specs

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request, os; r = urllib.request.urlopen('http://localhost:%s/health' % os.environ.get('BAA_PORT','8000')); assert r.status == 200" || exit 1

# 环境变量（运行时可通过 -e 覆盖）
# T-C4/T-C5 生产安全基线：匿名关闭、PDF AGPL 进程隔离开启、结构化日志
ENV BAA_PORT=8000
ENV BAA_WORKERS=2
ENV BAA_DATA_DIR=/app/data
ENV BAA_ALLOW_ANONYMOUS=0
ENV BAA_PDF_ISOLATION=1
ENV BAA_LOG_FORMAT=json
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8000

# 生产启动：Alembic 迁移 + Gunicorn + Uvicorn Worker
ENTRYPOINT ["./docker-entrypoint.sh"]
