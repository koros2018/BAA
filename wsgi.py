"""
BAA 生产部署入口
使用 Gunicorn + Uvicorn Worker 提供生产级并发能力

启动方式：
  # 开发模式（单进程）
  python src/api/baa_api.py

  # 生产模式（多 worker + 优雅重启）
  gunicorn src.api.baa_api:app -k uvicorn.workers.UvicornWorker -w 4 \
    --bind 0.0.0.0:8000 --timeout 120 --max-requests 10000 \
    --access-logfile data/logs/gunicorn-access.log \
    --error-logfile data/logs/gunicorn-error.log \
    --preload

  # 生产模式（热重载调试）
  gunicorn src.api.baa_api:app -k uvicorn.workers.UvicornWorker -w 4 \
    --bind 0.0.0.0:8000 --reload

环境变量：
  BAA_PORT      服务端口（默认 8000）
  BAA_WORKERS   Worker 数（默认 CPU 核数）
  BAA_TIMEOUT   请求超时秒数（默认 120）
"""
import sys
from pathlib import Path

# 确保项目根在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.baa_api import app

if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.getenv("BAA_PORT", "8000"))
    workers = int(os.getenv("BAA_WORKERS", os.cpu_count() or 4))

    uvicorn.run(
        "src.api.baa_api:app",
        host="0.0.0.0",
        port=port,
        workers=workers,
        log_config=None,
        access_log=False,
        log_level="info",
    )
