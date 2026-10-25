"""T-C3：API 指标 + 访问日志中间件。

按路由模板（scope["route"].path）分组标签，避免 file_id/task_id 等路径参数
造成标签基数爆炸；路由未匹配（404 静态/未知路径）回退到首两段路径。
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.baa_engine.observability import HTTP_DURATION, HTTP_REQUESTS, log_request


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return path
    raw = request.url.path
    parts = [p for p in raw.split("/") if p]
    return "/" + "/".join(parts[:2]) if parts else "/"


class MetricsMiddleware(BaseHTTPMiddleware):
    """记录每请求计数/耗时 + 结构化访问日志。"""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = _route_template(request)
            duration = time.time() - start
            HTTP_REQUESTS.labels(request.method, route, str(status)).inc()
            HTTP_DURATION.labels(request.method, route).observe(duration)
            client = request.client.host if request.client else ""
            log_request(request.method, route, status, duration * 1000, client)
