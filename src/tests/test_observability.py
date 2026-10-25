"""T-C3 可观测性单测：指标模块、/metrics 端点、JSON 结构化日志、告警规则。"""

import json
import logging
import time

import pytest
import yaml


def test_metrics_module_counters_and_render():
    from src.baa_engine import observability as obs

    obs.HTTP_REQUESTS.labels("GET", "/health", "200").inc()
    obs.HTTP_DURATION.labels("GET", "/health").observe(0.01)
    obs.PARSE_TOTAL.labels(result="success").inc()
    obs.PARSE_DURATION.observe(0.5)
    obs.REVIEW_DURATION.labels(endpoint="review").observe(1.2)
    obs.FINDINGS_TOTAL.labels(severity="critical").inc()
    obs.REVIEW_ERRORS.labels(code="PARSE_FAILED").inc()
    obs.RATE_LIMIT_REJECTED.inc()

    text = obs.render_metrics().decode()
    assert 'baa_http_requests_total{method="GET",route="/health",status="200"}' in text
    assert 'baa_parse_total{result="success"}' in text
    assert 'baa_findings_total{severity="critical"}' in text
    assert 'baa_review_errors_total{code="PARSE_FAILED"}' in text
    assert "baa_rate_limit_rejected_total" in text
    assert "baa_review_duration_seconds_bucket" in text


def test_queue_gauges_from_provider():
    from src.baa_engine import observability as obs

    obs.register_queue_stats_provider(
        lambda: {
            "queued_count": 3,
            "running_count": 1,
            "completed_count": 9,
            "failed_count": 2,
        }
    )
    obs.collect_queue_stats()
    text = obs.render_metrics().decode()
    assert "baa_queue_queued 3.0" in text
    assert "baa_queue_running 1.0" in text
    assert "baa_queue_completed 9.0" in text
    assert "baa_queue_failed 2.0" in text


def test_queue_provider_failure_does_not_break_render():
    from src.baa_engine import observability as obs

    def _boom():
        raise RuntimeError("db down")

    obs.register_queue_stats_provider(_boom)
    text = obs.render_metrics().decode()  # 不抛异常
    assert "baa_http_requests_total" in text
    obs.register_queue_stats_provider(None)


def test_json_formatter_outputs_searchable_fields():
    from src.baa_engine.observability import JsonFormatter, log_request

    formatter = JsonFormatter()
    record = logging.LogRecord(
        "baa.access", logging.INFO, __file__, 1, "GET /health -> 200", (), None
    )
    record.route = "/health"
    record.status = 200
    payload = json.loads(formatter.format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "baa.access"
    assert payload["route"] == "/health"
    assert payload["status"] == 200

    # log_request 不抛异常且产出 JSON 行
    log_request("POST", "/review", 200, 12.3, "127.0.0.1")


def test_setup_structured_logging_json_mode(monkeypatch):
    import io

    from src.baa_engine.observability import setup_structured_logging

    monkeypatch.setenv("BAA_LOG_FORMAT", "json")
    enabled = setup_structured_logging()
    assert enabled is True
    root = logging.getLogger()
    json_handlers = [
        h for h in root.handlers if h.formatter.__class__.__name__ == "JsonFormatter"
    ]
    assert json_handlers, "JSON handler 未挂载"
    # 清理：恢复无 JSON handler 状态，避免污染其他测试输出
    for h in json_handlers:
        root.removeHandler(h)


def test_setup_structured_logging_default_off(monkeypatch):
    from src.baa_engine.observability import setup_structured_logging

    monkeypatch.delenv("BAA_LOG_FORMAT", raising=False)
    assert setup_structured_logging() is False


def test_metrics_endpoint_exposed():
    from fastapi.testclient import TestClient

    from src.api.baa_api import app

    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "baa_http_requests_total" in body
    assert "baa_queue_queued" in body
    # /metrics 自身请求由中间件在响应后记录 → 第二次抓取可见
    body2 = client.get("/metrics").text
    assert 'route="/metrics"' in body2


def test_middleware_records_route_template_not_raw_path():
    """路径参数（如 order_id）必须被路由模板收敛，防止标签基数爆炸。"""
    from fastapi.testclient import TestClient

    from src.api.baa_api import app

    client = TestClient(app)
    client.get("/order/obs-test-12345")  # 触发一次带路径参数的请求
    body = client.get("/metrics").text
    assert 'route="/order/{order_id}"' in body
    assert "obs-test-12345" not in body


def test_alert_rules_yaml_valid():
    path = "k8s/prometheus-rules.yaml"
    doc = yaml.safe_load(open(path, encoding="utf-8"))
    assert doc["kind"] == "PrometheusRule"
    groups = doc["spec"]["groups"]
    assert len(groups) == 3
    alert_names = [r["alert"] for g in groups for r in g["rules"]]
    # 覆盖关键链路：API 错误/慢请求、解析、判定、限流、队列、可用性
    expected = {
        "BaaHighErrorRate",
        "BaaSlowRequests",
        "BaaPodDown",
        "BaaParseFailureSpike",
        "BaaReviewSlowP95",
        "BaaQueueBacklog",
        "BaaRateLimitSpike",
    }
    assert expected.issubset(set(alert_names))
    for g in groups:
        for r in g["rules"]:
            assert r.get("expr"), f"{r['alert']} 缺 expr"
            assert r.get("for"), f"{r['alert']} 缺 for"
