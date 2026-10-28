"""E3-T3: 接口级 RBAC 权限校验中间件。

验证请求的 API Key 是否具有访问特定端点所需的权限 scope。
"""

import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.api.api_globals import get_key_manager, API_KEYS, _anonymous_allowed

logger = logging.getLogger(__name__)

# 需要 admin scope 才能访问的路径前缀
_ADMIN_PATH_PREFIXES = (
    "/api/v1/admin/",
    "/api/v1/audit/",
    "/api/v1/rbac",
)


class RBACMiddleware(BaseHTTPMiddleware):
    """接口级 RBAC 权限校验中间件。

    逻辑：
    1. 无 key 且允许匿名 → 放行
    2. 无 key 且不允许匿名 → 401
    3. 有 key → 验证 scope，不足则 403
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        # 公开端点（无鉴权）
        if path.startswith("/health") or path == "/metrics":
            return await call_next(request)

        # 从 Authorization header 或 query 参数提取 key
        auth_header = request.headers.get("authorization", "")
        api_key = ""
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]
        elif "api_key" in request.query_params:
            api_key = request.query_params["api_key"]

        # 检查是否需要鉴权
        needs_auth = True
        for prefix in ("/api/v1/public", "/health", "/docs", "/redoc", "/openapi.json", "/api/v1/standards"):
            if path.startswith(prefix):
                needs_auth = False
                break

        # 无需鉴权的端点直接放行
        if not needs_auth:
            return await call_next(request)

        # 匿名访问控制
        if not api_key:
            if _anonymous_allowed():
                request.state.api_key = "anonymous"
                request.state.key_info = {"permission": "anonymous", "scopes": []}
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content={
                    "status": "error",
                    "error_code": "UNAUTHORIZED",
                    "message": "缺少 API Key",
                },
            )

        # 验证 key 并检查权限
        km = get_key_manager()
        key_info = km.validate_key(api_key)

        # 回退到静态 API_KEYS（向后兼容）
        if not key_info and api_key and api_key in API_KEYS:
            key_info = {
                "key_id": "static",
                "permission": "admin",
                "scopes": ["*"],
                "enabled": True,
            }

        if not key_info or not key_info.get("enabled", True):
            return JSONResponse(
                status_code=401,
                content={
                    "status": "error",
                    "error_code": "UNAUTHORIZED",
                    "message": "无效的 API Key",
                },
            )

        # 注入到 request.state，供后续路由使用
        request.state.api_key = api_key
        request.state.key_info = key_info

        # 检查 admin 路径是否需要 admin scope
        if any(path.startswith(p) for p in _ADMIN_PATH_PREFIXES):
            from src.baa_engine.api_key_manager import has_scope

            if not has_scope(key_info, "admin:write"):
                return JSONResponse(
                    status_code=403,
                    content={
                        "status": "error",
                        "error_code": "INSUFFICIENT_SCOPE",
                        "message": f"需要 admin:write 权限访问 {path}",
                        "required_scope": "admin:write",
                    },
                )

        return await call_next(request)
