"""
T-C3 可观测性：Prometheus 指标 + 结构化日志
================================================

指标（关键链路全覆盖）：
- API 链路：baa_http_requests_total{method,route,status}、
  baa_http_request_duration_seconds{method,route}（路由模板分组，防标签爆炸）
- 解析链路：baa_parse_duration_seconds、baa_parse_total{result}
- 判定链路：baa_review_duration_seconds{endpoint}、baa_findings_total{severity}、
  baa_review_errors_total{code}
- 限流：baa_rate_limit_rejected_total
- 队列：baa_queue_{queued,running,completed,failed}（采集时从注册 provider 读取，
  多副本下 running 为本副本视角，queued/completed/failed 为命名空间全局）

结构化日志：
- BAA_LOG_FORMAT=json 时 root logger 输出 JSON 行（ts/level/logger/message + extras），
  可被 Loki/ELK 检索；默认保持原有人类可读格式（开发友好）。

多副本注意：默认 REGISTRY 进程内聚合；k8s 多副本由 Prometheus 按 Pod 抓取，
不要在多副本间共享 REGISTRY（Gunicorn 多 worker 需 prometheus 多进程模式，
本服务单 worker + 多副本部署，无需启用）。
"""

import json
import logging
import os
import time
from typing import Callable, Optional

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# ── API 链路 ──────────────────────────────────────────────
HTTP_REQUESTS = Counter(
    "baa_http_requests_total",
    "HTTP 请求总数（按方法/路由模板/状态码）",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "baa_http_request_duration_seconds",
    "HTTP 请求耗时（秒）",
    ["method", "route"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

# ── 解析链路 ──────────────────────────────────────────────
PARSE_DURATION = Histogram(
    "baa_parse_duration_seconds",
    "图纸解析耗时（秒，DXF/DWG → 图元）",
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)
PARSE_TOTAL = Counter(
    "baa_parse_total",
    "图纸解析次数（result: success/failed）",
    ["result"],
)

# ── 判定链路 ──────────────────────────────────────────────
REVIEW_DURATION = Histogram(
    "baa_review_duration_seconds",
    "规范判定耗时（秒）",
    ["endpoint"],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)
FINDINGS_TOTAL = Counter(
    "baa_findings_total",
    "审查发现条数（按严重度）",
    ["severity"],
)
REVIEW_ERRORS = Counter(
    "baa_review_errors_total",
    "审查错误次数（按 error_code）",
    ["code"],
)

# ── 限流 ─────────────────────────────────────────────────
RATE_LIMIT_REJECTED = Counter(
    "baa_rate_limit_rejected_total",
    "被分布式限流拒绝的请求数（429）",
)

# ── 任务队列（Gauge，采集时回调 provider） ──────────────────
_queue_stats_provider: Optional[Callable[[], dict]] = None

QUEUE_QUEUED = Gauge("baa_queue_queued", "排队中的审查任务数（命名空间全局）")
QUEUE_RUNNING = Gauge("baa_queue_running", "本副本运行中的审查任务数")
QUEUE_COMPLETED = Gauge("baa_queue_completed", "已完成审查任务数（命名空间全局）")
QUEUE_FAILED = Gauge("baa_queue_failed", "失败审查任务数（命名空间全局）")


def register_queue_stats_provider(provider: Callable[[], dict]) -> None:
    """注册队列统计回调（由 api 层注入 _review_queue.stats）。"""
    global _queue_stats_provider
    _queue_stats_provider = provider


def collect_queue_stats() -> None:
    """采集前刷新队列 Gauge（/metrics 端点与告警共用同一读数）。"""
    if _queue_stats_provider is None:
        return
    try:
        stats = _queue_stats_provider() or {}
        QUEUE_QUEUED.set(float(stats.get("queued_count", 0) or 0))
        QUEUE_RUNNING.set(float(stats.get("running_count", 0) or 0))
        QUEUE_COMPLETED.set(float(stats.get("completed_count", 0) or 0))
        QUEUE_FAILED.set(float(stats.get("failed_count", 0) or 0))
    except Exception:  # 采集失败不影响 /metrics 其他指标
        logger = logging.getLogger(__name__)
        logger.warning("[T-C3] 队列指标采集失败", exc_info=True)


def render_metrics() -> bytes:
    """生成 Prometheus 文本格式指标（采集前刷新队列读数）。"""
    collect_queue_stats()
    return generate_latest()


__all__ = [
    "CONTENT_TYPE_LATEST",
    "HTTP_REQUESTS",
    "HTTP_DURATION",
    "PARSE_DURATION",
    "PARSE_TOTAL",
    "REVIEW_DURATION",
    "FINDINGS_TOTAL",
    "REVIEW_ERRORS",
    "RATE_LIMIT_REJECTED",
    "QUEUE_QUEUED",
    "QUEUE_RUNNING",
    "QUEUE_COMPLETED",
    "QUEUE_FAILED",
    "register_queue_stats_provider",
    "collect_queue_stats",
    "render_metrics",
    "JsonFormatter",
    "setup_structured_logging",
    "log_request",
]


# ── 结构化日志 ────────────────────────────────────────────

_ACCESS_LOGGER = logging.getLogger("baa.access")


class JsonFormatter(logging.Formatter):
    """JSON 行日志：ts/level/logger/message + extras（可检索字段）。"""

    _RESERVED = set(
        logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
    ) | {"taskName"}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": round(record.created, 3),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self._RESERVED:
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_structured_logging(force: bool = False) -> bool:
    """按 BAA_LOG_FORMAT=json 将 root logger 切换为 JSON 输出。

    返回是否启用。默认（非 json）不改动既有 logging 配置。
    """
    fmt = os.getenv("BAA_LOG_FORMAT", "").strip().lower()
    if fmt != "json" and not force:
        return False
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if getattr(h, "_baa_keep", False)]
    root.addHandler(handler)
    if root.level > logging.INFO:
        root.setLevel(logging.INFO)
    return True


def log_request(
    method: str, route: str, status: int, duration_ms: float, client: str = ""
) -> None:
    """访问日志（JSON 模式下为结构化字段，便于按 route/status 检索）。"""
    _ACCESS_LOGGER.info(
        "%s %s -> %s (%.1fms)",
        method,
        route,
        status,
        duration_ms,
        extra={
            "method": method,
            "route": route,
            "status": status,
            "duration_ms": round(duration_ms, 1),
            "client": client,
        },
    )
