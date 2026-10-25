#!/bin/sh
# T-C5：生产容器入口——先跑 Alembic 迁移再起服务（一键就绪）
set -e

echo "[entrypoint] alembic upgrade head (BAA_DATABASE_URL=${BAA_DATABASE_URL:-<default sqlite>})"
python -m alembic upgrade head

echo "[entrypoint] start gunicorn (workers=${BAA_WORKERS:-2}, port=${BAA_PORT:-8000})"
exec gunicorn src.api.baa_api:app \
    -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${BAA_PORT:-8000} \
    --timeout 120 \
    --max-requests 10000 \
    --workers ${BAA_WORKERS:-2} \
    --access-logfile - \
    --error-logfile - \
    --preload
