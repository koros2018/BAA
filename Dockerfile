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

# 复制依赖清单
COPY requirements.txt pyproject.toml ./

# 安装所有依赖到 /install
RUN pip install --user --no-cache-dir -r requirements.txt

# ── 第二阶段：运行环境 ────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="BAA - Blueprint AI Agent"
LABEL org.opencontainers.image.description="图纸合规智能体 - DXF/DWG 图纸 AI 审查系统"
LABEL org.opencontainers.image.version="1.10.0"
LABEL org.opencontainers.image.source="https://github.com/koros2018/BAA"

# 系统运行依赖（ezdwg/ezdxf 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libc6 \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制已安装的包
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

WORKDIR /app

# 复制项目代码（排除开发/测试文件）
COPY . .

# 清理开发文件以缩小镜像
RUN rm -rf \
    .git \
    .venv \
    venv \
    .pytest_cache \
    __pycache__ \
    */__pycache__ \
    */*/__pycache__ \
    .gitignore \
    .env.example \
    conftest.py \
    scripts/ \
    docs/ \
    data/logs/

# 创建数据目录（卷挂载点）
RUN mkdir -p /app/data/files /app/data/models /app/data/logs /app/data/specs

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request; r = urllib.request.urlopen('http://localhost:${BAA_PORT:-8000}/health'); assert r.status == 200" || exit 1

# 环境变量（运行时可通过 -e 覆盖）
ENV BAA_PORT=8000
ENV BAA_WORKERS=4
ENV BAA_DATA_DIR=/app/data
ENV BAA_API_KEY=
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8000

# 生产启动：Gunicorn + Uvicorn Worker
ENTRYPOINT ["gunicorn", "src.api.baa_api:app", \
    "-k", "uvicorn.workers.UvicornWorker", \
    "--bind", "0.0.0.0:8000", \
    "--timeout", "120", \
    "--max-requests", "10000", \
    "--access-logfile", "-", \
    "--error-logfile", "-", \
    "--preload"]