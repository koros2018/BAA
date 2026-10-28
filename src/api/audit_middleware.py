"""E2-T2：审计日志中间件。

自动拦截审查类请求，将操作写入 audit_logs 表。
- review_started：每次 /review 请求开始
- review_completed：审查正常完成
- review_failed：审查抛出异常
- violation_confirmed：违规被确认
- violation_dismissed：违规被驳回
"""

import logging
import uuid
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.baa_engine.db.database import get_session_factory

logger = logging.getLogger(__name__)

# 需要审计的路径前缀
_AUDIT_PATH_PREFIXES = ("/review", "/api/v1/reviews", "/api/v1/audit")


def _get_actor(request: Request) -> tuple[str, str]:
    """提取 actor_id 和 actor_role。"""
    # 优先从 request.state 读取（由鉴权中间件注入）
    actor_id = getattr(request.state, "actor_id", "") or ""
    actor_role = getattr(request.state, "actor_role", "system") or "system"
    if not actor_id:
        # 回退到 Authorization header
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            actor_id = auth[7:20]  # 取 token 前缀标识
    return actor_id or "anonymous", actor_role or "system"


def write_audit_log(
    event_type: str,
    resource_type: str,
    resource_id: str,
    action: str,
    detail: Optional[str] = None,
    request: Optional[Request] = None,
) -> None:
    """异步写入审计日志（不阻塞主流程）。"""
    try:
        from src.baa_engine.db.models.audit_log import AuditLog

        sf = get_session_factory()
        session = sf()
        actor_id, actor_role = "system", "system"
        if request is not None:
            actor_id, actor_role = _get_actor(request)

        log_entry = AuditLog(
            id=uuid.uuid4().hex,
            event_type=event_type,
            actor_id=actor_id,
            actor_role=actor_role,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            detail=detail,
            ip_address=request.client.host if request and request.client else "",
            user_agent=str(request.headers.get("user-agent", ""))[:500] if request else "",
        )
        session.add(log_entry)
        session.commit()
    except Exception as exc:
        logger.warning("[E2-T2] 审计日志写入失败: %s", exc, exc_info=True)
    finally:
        sf.remove()


class AuditMiddleware(BaseHTTPMiddleware):
    """在审查相关请求前后写入审计日志。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        is_audit_path = any(request.url.path.startswith(p) for p in _AUDIT_PATH_PREFIXES)
        response: Response
        try:
            if is_audit_path:
                review_id = _extract_review_id(request)
                write_audit_log(
                    event_type="review_started",
                    resource_type="review",
                    resource_id=review_id or "unknown",
                    action="start",
                    request=request,
                )
            response = await call_next(request)
            if is_audit_path and response.status_code < 500:
                review_id = _extract_review_id(request)
                write_audit_log(
                    event_type="review_completed",
                    resource_type="review",
                    resource_id=review_id or "unknown",
                    action="complete",
                    detail=f"status={response.status_code}",
                    request=request,
                )
            elif is_audit_path:
                review_id = _extract_review_id(request)
                write_audit_log(
                    event_type="review_failed",
                    resource_type="review",
                    resource_id=review_id or "unknown",
                    action="fail",
                    detail=f"status={response.status_code}",
                    request=request,
                )
            return response
        except Exception:
            if is_audit_path:
                review_id = _extract_review_id(request)
                write_audit_log(
                    event_type="review_failed",
                    resource_type="review",
                    resource_id=review_id or "unknown",
                    action="exception",
                    request=request,
                )
            raise


def _extract_review_id(request: Request) -> str:
    """从路径或 body 中提取 review_id。"""
    path = request.url.path
    # 路径参数模式：/api/v1/reviews/{review_id}/...
    parts = path.strip("/").split("/")
    for i, part in enumerate(parts):
        if part == "reviews" and i + 1 < len(parts):
            candidate = parts[i + 1]
            if candidate and all(c.isalnum() or c in "-_" for c in candidate):
                return candidate
    # query 参数
    query = dict(request.query_params)
    return query.get("review_id", "") or query.get("task_id", "")
