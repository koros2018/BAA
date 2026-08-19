"""
P119 违规审核工作流 — 后端单元测试

覆盖：
1. 初始化条目（从 details 批量创建）
2. confirm / dismiss / pending / note 状态转换
3. dismiss 误报 → feedback_engine 自动入库
4. stats 统计
5. 重复调用幂等性（INSERT OR REPLACE）
6. 错误状态拒绝
"""

import pytest
import uuid

from src.baa_engine.collab import audit


@pytest.fixture
def review_id():
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def sample_details():
    return [
        {"id": "e1", "entity_id": "door-1", "function_id": "DIM-006", "result": "FAIL"},
        {"id": "e2", "entity_id": "door-2", "function_id": "DIM-006", "result": "FAIL"},
        {"id": "e3", "entity_id": "room-1", "function_id": "AREA-001", "result": "PASS"},  # 应被跳过
        {"id": "e4", "entity_id": "exit-1", "function_id": "EXIST-001", "result": "CONFIRMED"},
    ]


class TestP119CreateItems:
    def test_creates_only_fail_and_confirmed(self, review_id, sample_details):
        count = audit.create_items_from_review(review_id, sample_details)
        assert count == 3  # e1, e2, e4（e3 PASS 被跳过）

    def test_items_in_db(self, review_id, sample_details):
        audit.create_items_from_review(review_id, sample_details)
        items = audit.get_items(review_id)
        assert len(items) == 3
        statuses = {i["status"] for i in items}
        assert statuses == {"unreviewed"}

    def test_idempotent_insert(self, review_id, sample_details):
        audit.create_items_from_review(review_id, sample_details)
        audit.create_items_from_review(review_id, sample_details)
        items = audit.get_items(review_id)
        assert len(items) == 3  # INSERT OR REPLACE，不重复

    def test_empty_details(self, review_id):
        count = audit.create_items_from_review(review_id, [])
        assert count == 0


class TestP119StatusTransitions:
    def _init(self, review_id, sample_details):
        audit.create_items_from_review(review_id, sample_details)
        items = audit.get_items(review_id)
        return items

    def test_confirm(self, review_id, sample_details):
        items = self._init(review_id, sample_details)
        item_id = items[0]["id"]
        result = audit.confirm_item(item_id, user_id="engineer-1", note="实测宽度确认不足")
        assert result["status"] == "confirmed"
        assert result["user_id"] == "engineer-1"
        assert result["note"] == "实测宽度确认不足"
        assert result["reviewed_at"] is not None

    def test_dismiss_requires_reason(self, review_id, sample_details):
        items = self._init(review_id, sample_details)
        item_id = items[1]["id"]
        with pytest.raises(ValueError, match="reason"):
            audit.dismiss_item(item_id, reason="", user_id="e1")

    def test_dismiss(self, review_id, sample_details):
        items = self._init(review_id, sample_details)
        item_id = items[1]["id"]
        result = audit.dismiss_item(item_id, reason="实测宽度合格，图纸尺寸有误差", user_id="e2")
        assert result["status"] == "dismissed"
        assert result["reason"] == "实测宽度合格，图纸尺寸有误差"

    def test_pending(self, review_id, sample_details):
        items = self._init(review_id, sample_details)
        item_id = items[2]["id"]
        result = audit.pending_item(item_id, user_id="e3", note="需要现场复核")
        assert result["status"] == "pending"

    def test_note_update(self, review_id, sample_details):
        items = self._init(review_id, sample_details)
        item_id = items[0]["id"]
        audit.confirm_item(item_id)  # 先确认
        result = audit.update_note(item_id, note="补充说明：已复核", user_id="e4")
        assert result["status"] == "confirmed"  # 不改变 status
        assert result["note"] == "补充说明：已复核"

    def test_invalid_status_raises(self, review_id, sample_details):
        items = self._init(review_id, sample_details)
        item_id = items[0]["id"]
        with pytest.raises(ValueError, match="非法审核状态"):
            # 通过 _update_item 模拟（不暴露给外部）
            audit._update_item(item_id, "invalid", user_id="e")

    def test_nonexistent_item_returns_none(self):
        assert audit.confirm_item("nonexistent-id") is None


class TestP119Stats:
    def test_stats_after_mix(self, review_id, sample_details):
        audit.create_items_from_review(review_id, sample_details)
        items = audit.get_items(review_id)
        item_ids = [i["id"] for i in items]

        audit.confirm_item(item_ids[0])
        audit.dismiss_item(item_ids[1], reason="误报")
        audit.pending_item(item_ids[2])

        stats = audit.get_stats(review_id)
        assert stats["total"] == 3
        assert stats["confirmed"] == 1
        assert stats["dismissed"] == 1
        assert stats["pending"] == 1
        assert stats.get("unreviewed", 0) == 0

    def test_stats_empty_review(self, review_id):
        audit.create_items_from_review(review_id, [])
        stats = audit.get_stats(review_id)
        assert stats["total"] == 0


class TestP119FeedbackIntegration:
    def test_dismiss_creates_feedback(self, review_id, sample_details):
        audit.create_items_from_review(review_id, sample_details)
        items = audit.get_items(review_id)
        item_id = items[0]["id"]
        audit.dismiss_item(item_id, reason="实测合格", user_id="e1")

        from src.baa_engine.feedback_engine import FeedbackManager
        from pathlib import Path

        db_dir = Path(__file__).resolve().parent.parent.parent / "data"
        fb = FeedbackManager(db_dir)
        all_fbs = fb.list_all(limit=1000)
        # 通过 description 中的 item_id 精确定位
        item_id = items[0]["id"]
        p119_fbs = [r for r in all_fbs[0] if item_id in r.get("description", "")]
        assert len(p119_fbs) >= 1
        last = p119_fbs[-1]
        assert last["reason"] == "实测合格"