"""
P71: Webhook 通知测试

覆盖：
- build_webhook_payload: generic / feishu / dingtalk 三种格式
- task_queue.complete: 触发 webhook（本地 import 路径 monkeypatch）
- task_queue.fail: 触发失败通知
- /review API 端点 webhook 参数透传
- /review-from-data 端点 webhook 参数透传
"""

import sys
import os
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ═══════════════════════════════════════════════════════════
# Webhook payload 构建器
# ═══════════════════════════════════════════════════════════


class TestBuildWebhookPayload:
    """build_webhook_payload 三种格式"""

    def test_generic_format(self):
        """generic 格式包含 task_id/status/result/error"""
        from src.baa_engine.webhooks import build_webhook_payload

        payload = build_webhook_payload(
            task_id="review-abc123",
            file_id="file-xyz",
            status="completed",
            result={"violations": 5, "score": 85.0},
            error=None,
            webhook_type="generic",
        )
        assert isinstance(payload, dict)
        assert payload["task_id"] == "review-abc123"
        assert payload["file_id"] == "file-xyz"
        assert payload["status"] == "completed"
        assert "result" in payload
        assert "completed_at" in payload

    def test_generic_with_error(self):
        """generic 格式 error 字段非空"""
        from src.baa_engine.webhooks import build_webhook_payload

        payload = build_webhook_payload(
            task_id="review-abc123",
            file_id="file-xyz",
            status="failed",
            result=None,
            error="Timeout",
            webhook_type="generic",
        )
        assert payload["status"] == "failed"
        assert payload["error"] == "Timeout"

    def test_feishu_format(self):
        """feishu 格式包含卡片消息结构"""
        from src.baa_engine.webhooks import build_webhook_payload

        payload = build_webhook_payload(
            task_id="review-abc123",
            file_id="file-xyz",
            status="completed",
            result={"violations": 5, "score": 85.0},
            error=None,
            webhook_type="feishu",
        )
        assert isinstance(payload, dict)
        # 飞书卡片消息格式：含 header 或 msg_type 或 elements
        has_card = "header" in payload or "msg_type" in payload or "elements" in payload
        assert has_card, "feishu payload should have card structure"

    def test_dingtalk_format(self):
        """dingtalk 格式包含 markdown/文本消息结构"""
        from src.baa_engine.webhooks import build_webhook_payload

        payload = build_webhook_payload(
            task_id="review-abc123",
            file_id="file-xyz",
            status="completed",
            result={"violations": 5, "score": 85.0},
            error=None,
            webhook_type="dingtalk",
        )
        assert isinstance(payload, dict)
        # 钉钉消息格式
        has_msg = "msgtype" in payload or "text" in payload or "markdown" in payload
        assert has_msg, "dingtalk payload should have text/markdown structure"

    def test_unknown_webhook_type_falls_back_to_generic(self):
        """未知 webhook_type 降级为 generic"""
        from src.baa_engine.webhooks import build_webhook_payload

        payload = build_webhook_payload(
            task_id="review-abc123",
            file_id="file-xyz",
            status="completed",
            result=None,
            error=None,
            webhook_type="wechat",
        )
        assert "task_id" in payload
        assert "status" in payload


# ═══════════════════════════════════════════════════════════
# TaskQueue webhook 触发
# ═══════════════════════════════════════════════════════════


class TestTaskQueueWebhook:
    """task_queue.complete/fail 触发 webhook

    complete()/fail() 内部用 `from .webhooks import trigger_webhook` 本地导入，
    所以 monkeypatch 要打在 baa_engine.webhooks 模块上。
    """

    def _make_running_task(self, rq, webhook_url=None, webhook_type="generic"):
        """创建并启动一个任务到 running 状态"""
        rq.enqueue("file-1", webhook_url=webhook_url, webhook_type=webhook_type)
        # 用 run_until_complete 等待 dequeue，避免 coroutine warning
        loop = asyncio.new_event_loop()
        try:
            task = loop.run_until_complete(rq.dequeue())
        finally:
            loop.close()
        task.status = "running"
        rq._running_count = 1
        return task.task_id

    def test_complete_triggers_webhook(self):
        """complete 时 webhook_url 非空应触发 webhook"""
        from src.baa_engine.task_queue import ReviewQueue

        rq = ReviewQueue(max_concurrent=1)
        task_id = self._make_running_task(rq, webhook_url="https://example.com/webhook")

        trigger_calls = []

        def fake_trigger(url, payload, **kw):
            trigger_calls.append({"url": url, "payload": payload})
            return None

        with patch("src.baa_engine.webhooks.trigger_webhook", fake_trigger):
            rq.complete(task_id, {"violations": 5})

        assert len(trigger_calls) == 1
        assert trigger_calls[0]["url"] == "https://example.com/webhook"

    def test_complete_no_webhook_when_empty_url(self):
        """webhook_url 为空时不触发 webhook"""
        from src.baa_engine.task_queue import ReviewQueue

        rq = ReviewQueue(max_concurrent=1)
        task_id = self._make_running_task(rq, webhook_url=None)

        call_count = [0]

        def fake_trigger(url, payload, **kw):
            call_count[0] += 1
            return None

        with patch("src.baa_engine.webhooks.trigger_webhook", fake_trigger):
            rq.complete(task_id, {"violations": 0})

        assert call_count[0] == 0

    def test_fail_triggers_webhook(self):
        """fail 时触发失败 webhook"""
        from src.baa_engine.task_queue import ReviewQueue

        rq = ReviewQueue(max_concurrent=1)
        task_id = self._make_running_task(rq, webhook_url="https://example.com/webhook")

        call_count = [0]

        def fake_trigger(url, payload, **kw):
            call_count[0] += 1
            return None

        with patch("src.baa_engine.webhooks.trigger_webhook", fake_trigger):
            rq.fail(task_id, "Timeout")

        assert call_count[0] == 1

    def test_enqueue_stores_webhook_type(self):
        """enqueue 应保存 webhook_type"""
        from src.baa_engine.task_queue import ReviewQueue

        rq = ReviewQueue(max_concurrent=1)
        task_id, _ = rq.enqueue(
            "file-1", webhook_url="https://example.com/webhook", webhook_type="feishu"
        )
        task = rq._tasks[task_id]
        assert task.webhook_url == "https://example.com/webhook"
        assert task.webhook_type == "feishu"

    def test_enqueue_default_webhook_type(self):
        """enqueue 默认 webhook_type 为 generic"""
        from src.baa_engine.task_queue import ReviewQueue

        rq = ReviewQueue(max_concurrent=1)
        task_id, _ = rq.enqueue("file-1", webhook_url="https://example.com/webhook")
        task = rq._tasks[task_id]
        assert task.webhook_type == "generic"


# ═══════════════════════════════════════════════════════════
# /review API webhook 参数透传
# ═══════════════════════════════════════════════════════════


class TestReviewEndpointWebhook:
    """/review 和 /review-from-data 端点正确接收 webhook 参数"""

    @pytest.fixture(autouse=True)
    def _api_key(self):
        """允许匿名访问（verify_api_key 在 API_KEYS 为空时走匿名路径）"""
        import src.api.api_globals as ag

        saved = set(ag.API_KEYS)
        ag.API_KEYS.clear()
        yield
        ag.API_KEYS.update(saved)

    def test_review_accepts_webhook_params(self):
        """/review 端点应接受 webhook_url 和 webhook_type 参数"""
        from fastapi.testclient import TestClient
        from src.api.baa_api import app

        client = TestClient(app)
        response = client.post(
            "/review?webhook_url=https://example.com/webhook&webhook_type=feishu",
            files={"file": ("test.dxf", b"mock dxf content", "application/dxf")},
            headers={"Authorization": "***"},
        )
        # 200/503/400 都正常（文件是 mock 内容，可能解析失败）
        assert response.status_code in (200, 400, 503)

    def test_review_from_data_accepts_webhook_in_body(self):
        """/review-from-data 应接受 body 中的 webhook_url/webhook_type"""
        from fastapi.testclient import TestClient
        from src.api.baa_api import app

        client = TestClient(app)

        sample_entities = [
            {
                "id": "door_001",
                "type": "door",
                "layer": "E-DOOR",
                "bbox": {"x": 0, "y": 0, "width": 0.9, "height": 2.1},
                "width": 0.9,
                "height": 2.1,
                "center": [0.45, 1.05],
                "attributes": {},
            }
        ]

        with patch("src.api.review.review_routes._get_fr") as mock_fr:
            mock_fr.return_value.list_all = MagicMock(return_value=[])
            response = client.post(
                "/review-from-data",
                json={
                    "entities": sample_entities,
                    "building_type": "civil",
                    "webhook_url": "https://example.com/webhook",
                    "webhook_type": "dingtalk",
                },
                headers={"Authorization": "***"},
            )

        assert response.status_code in (200, 503)
        if response.status_code == 200:
            data = response.json()
            # task_id 应在 response 顶层（P69 修复）
            assert "task_id" in data
            # queue_info 也应含 task_id
            assert "queue_info" in data
            assert data["queue_info"]["task_id"] == data["task_id"]
