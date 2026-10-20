"""T-B6 工作流闭环 — 审查会话状态机单测（T1）

覆盖：
- 流转表完备性（所有状态均有定义）
- 全链路合法流转 draft→…→archived
- 非法流转 / 未知状态拒绝
- in_progress 直达 rectifying（直接整改）
- approved/rejected 时 completed_at 落值
- archived 为终态
"""

import pytest

from src.baa_engine.team_collab.manager import CollaborationManager
from src.baa_engine.team_collab.models import REVIEW_STATUS_TRANSITIONS, ReviewStatus


@pytest.fixture()
def mgr(tmp_path):
    """独立临时库；重置单例保证用例隔离。"""
    CollaborationManager._instance = None
    CollaborationManager._initialized = False
    manager = CollaborationManager(db_path=str(tmp_path / "collab_t1.db"))
    yield manager
    CollaborationManager._instance = None
    CollaborationManager._initialized = False


def _make_session(mgr):
    """注册用户→建项目→建审查会话，返回 (user_id, review_session)。"""
    user, msg = mgr.register_user("tester", "pass123456")
    assert user, msg
    project, msg = mgr.create_project("测试项目", user["id"])
    assert project, msg
    rs, msg = mgr.create_review_session(project["id"], user["id"], name="工作流测试")
    assert rs, msg
    return user["id"], rs


def _walk(mgr, sid, uid, statuses):
    """依次流转到指定状态，全部必须成功。"""
    for target in statuses:
        ok, msg = mgr.update_review_session_status(sid, uid, target.value)
        assert ok, f"{target.value}: {msg}"


def test_transition_table_covers_all_statuses():
    """流转表必须覆盖 ReviewStatus 的每个取值。"""
    for s in ReviewStatus:
        assert s.value in REVIEW_STATUS_TRANSITIONS


def test_full_loop_happy_path(mgr):
    """全链路：draft→pending→in_progress→rejected→rectifying→rechecking→approved→archived。"""
    uid, rs = _make_session(mgr)
    _walk(
        mgr,
        rs["id"],
        uid,
        [
            ReviewStatus.PENDING,
            ReviewStatus.IN_PROGRESS,
            ReviewStatus.REJECTED,
            ReviewStatus.RECTIFYING,
            ReviewStatus.RECHECKING,
            ReviewStatus.APPROVED,
            ReviewStatus.ARCHIVED,
        ],
    )
    assert mgr.get_review_session(rs["id"], uid)["status"] == ReviewStatus.ARCHIVED.value


def test_in_progress_to_rectifying_direct(mgr):
    """进行中可直接进入整改（无需先驳回）。"""
    uid, rs = _make_session(mgr)
    _walk(
        mgr,
        rs["id"],
        uid,
        [ReviewStatus.PENDING, ReviewStatus.IN_PROGRESS, ReviewStatus.RECTIFYING],
    )
    assert mgr.get_review_session(rs["id"], uid)["status"] == ReviewStatus.RECTIFYING.value


def test_illegal_transitions_rejected(mgr):
    """draft 阶段非法流转一律拒绝且状态不变。"""
    uid, rs = _make_session(mgr)
    for bad in (
        ReviewStatus.APPROVED,
        ReviewStatus.ARCHIVED,
        ReviewStatus.REJECTED,
        ReviewStatus.RECTIFYING,
    ):
        ok, msg = mgr.update_review_session_status(rs["id"], uid, bad.value)
        assert not ok
        assert "非法状态流转" in msg
        assert mgr.get_review_session(rs["id"], uid)["status"] == ReviewStatus.DRAFT.value


def test_recheck_cycle_requires_rectifying(mgr):
    """rejected 后必须经 rectifying→rechecking 才能再次 approved/rejected。"""
    uid, rs = _make_session(mgr)
    _walk(mgr, rs["id"], uid, [ReviewStatus.PENDING, ReviewStatus.IN_PROGRESS, ReviewStatus.REJECTED])
    ok, msg = mgr.update_review_session_status(rs["id"], uid, ReviewStatus.APPROVED.value)
    assert not ok
    assert "非法状态流转" in msg
    ok, msg = mgr.update_review_session_status(rs["id"], uid, ReviewStatus.RECTIFYING.value)
    assert ok, msg
    ok, msg = mgr.update_review_session_status(rs["id"], uid, ReviewStatus.APPROVED.value)
    assert not ok  # rectifying 只能去 rechecking
    ok, msg = mgr.update_review_session_status(rs["id"], uid, ReviewStatus.RECHECKING.value)
    assert ok, msg
    ok, msg = mgr.update_review_session_status(rs["id"], uid, ReviewStatus.APPROVED.value)
    assert ok, msg
    assert mgr.get_review_session(rs["id"], uid)["completed_at"] > 0


def test_unknown_status_rejected(mgr):
    """未知状态字符串直接拒绝。"""
    uid, rs = _make_session(mgr)
    ok, msg = mgr.update_review_session_status(rs["id"], uid, "bogus")
    assert not ok
    assert "未知状态" in msg


def test_archived_is_terminal(mgr):
    """归档为终态，不可再流转。"""
    uid, rs = _make_session(mgr)
    _walk(
        mgr,
        rs["id"],
        uid,
        [ReviewStatus.PENDING, ReviewStatus.IN_PROGRESS, ReviewStatus.APPROVED, ReviewStatus.ARCHIVED],
    )
    ok, msg = mgr.update_review_session_status(rs["id"], uid, ReviewStatus.PENDING.value)
    assert not ok
    assert "非法状态流转" in msg


def test_completed_at_on_rejected(mgr):
    """rejected（初审/复查）同样写入 completed_at。"""
    uid, rs = _make_session(mgr)
    _walk(mgr, rs["id"], uid, [ReviewStatus.PENDING, ReviewStatus.IN_PROGRESS, ReviewStatus.REJECTED])
    assert mgr.get_review_session(rs["id"], uid)["completed_at"] > 0


def test_draft_start_state(mgr):
    """新建审查会话初始状态为 draft。"""
    uid, rs = _make_session(mgr)
    assert rs["status"] == ReviewStatus.DRAFT.value



# ---------------- T2 整改记录 ----------------

from src.baa_engine.team_collab.rectification import (  # noqa: E402
    create_rectifications,
    list_rectifications,
    update_rectification,
)


def test_rectification_create_batch_and_list(mgr):
    """批量登记整改记录并可列出，初始状态 pending。"""
    uid, rs = _make_session(mgr)
    records, msg = create_rectifications(
        mgr,
        rs["id"],
        uid,
        [
            {"clause_id": "6.1.2", "entity_id": "E1", "action": "修改墙线厚度", "owner": uid},
            {"clause_id": "6.2.1", "entity_id": "E2", "action": "补充疏散标识"},
        ],
    )
    assert records and len(records) == 2, msg
    listed, msg = list_rectifications(mgr, rs["id"], uid)
    assert len(listed) == 2, msg
    assert all(r["status"] == "pending" for r in listed)
    assert {r["clause_id"] for r in listed} == {"6.1.2", "6.2.1"}


def test_rectification_single_item_body(mgr):
    """body 本身为单条（无 items 键）也可登记。"""
    uid, rs = _make_session(mgr)
    records, msg = create_rectifications(mgr, rs["id"], uid, [{"clause_id": "6.1.2"}])
    assert records and len(records) == 1, msg


def test_rectification_update_done(mgr):
    """整改方更新状态为 done 并写备注。"""
    uid, rs = _make_session(mgr)
    records, _ = create_rectifications(mgr, rs["id"], uid, [{"clause_id": "6.1.2"}])
    rid = records[0]["id"]
    rec, msg = update_rectification(mgr, rid, uid, {"status": "done", "note": "已修正墙厚"})
    assert rec["status"] == "done", msg
    assert rec["note"] == "已修正墙厚"
    listed, _ = list_rectifications(mgr, rs["id"], uid)
    assert listed[0]["status"] == "done"


def test_rectification_update_invalid_status(mgr):
    """非法整改状态被拒绝。"""
    uid, rs = _make_session(mgr)
    records, _ = create_rectifications(mgr, rs["id"], uid, [{"clause_id": "6.1.2"}])
    ok, msg = update_rectification(mgr, records[0]["id"], uid, {"status": "x"})
    assert ok is None
    assert "不支持的整改状态" in msg


def test_rectification_permission(mgr):
    """非项目成员：登记需 EDIT（拒绝）、更新需 COMMENT（拒绝）。"""
    uid, rs = _make_session(mgr)
    other, msg = mgr.register_user("outsider", "pass123456")
    assert other, msg
    rec, msg = create_rectifications(mgr, rs["id"], other["id"], [{"clause_id": "6.1.2"}])
    assert rec is None
    assert msg == "无权限"
    records, _ = create_rectifications(mgr, rs["id"], uid, [{"clause_id": "6.1.2"}])
    ok, msg = update_rectification(mgr, records[0]["id"], other["id"], {"status": "done"})
    assert ok is None
    assert msg == "无权限"


def test_rectification_session_not_found(mgr):
    """会话不存在时登记/列表均报错。"""
    uid, _ = _make_session(mgr)
    rec, msg = create_rectifications(mgr, "no-such-session", uid, [{"clause_id": "6.1.2"}])
    assert rec is None
    assert msg == "会话不存在"
    listed, msg = list_rectifications(mgr, "no-such-session", uid)
    assert listed is None
    assert msg == "会话不存在"



# ---------------- T3 复查 ----------------

from src.baa_engine.team_collab import recheck as recheck_mod  # noqa: E402
from src.baa_engine.team_collab.models import ReviewSession  # noqa: E402, F811

F_A = {"clause_id": "6.1.2", "entity_id": "E1", "func_id": "F1", "severity": "major"}
F_B = {"clause_id": "6.2.1", "entity_id": "E2", "func_id": "F2", "severity": "critical"}
F_C = {"clause_id": "6.3.1", "entity_id": "", "func_id": "F3", "severity": "low"}


def test_recheck_baseline_and_counts(mgr, monkeypatch):
    """首次复查（无快照）：全部计为 new；状态流转到 rechecking；快照落盘。"""
    uid, rs = _make_session(mgr)
    # 先走合法路径到 rectifying：in_progress 直达整改
    _walk(mgr, rs["id"], uid, [ReviewStatus.PENDING, ReviewStatus.IN_PROGRESS, ReviewStatus.RECTIFYING])
    # 会话需关联 file_ids：直接置库
    db = mgr._get_session()
    row = db.query(ReviewSession).filter(ReviewSession.id == rs["id"]).first()
    row.file_ids = ["fake-file"]
    db.commit()
    mgr._close_session(db)

    monkeypatch.setattr(recheck_mod, "run_findings_for_file", lambda fid, bt="civil": [dict(F_A), dict(F_B)])
    result, msg = recheck_mod.recheck_session(mgr, rs["id"], uid)
    assert result, msg
    cmp = result["comparison"]
    assert cmp["new"]["count"] == 2 and cmp["resolved"]["count"] == 0 and cmp["persisted"]["count"] == 0
    detail = mgr.get_review_session(rs["id"], uid)
    assert detail["status"] == ReviewStatus.RECHECKING.value
    assert len(detail["result_summary"]["details"]) == 2


def test_recheck_resolved_persisted(mgr, monkeypatch):
    """二次复查：部分整改后 resolved/persisted 正确。"""
    uid, rs = _make_session(mgr)
    _walk(mgr, rs["id"], uid, [ReviewStatus.PENDING, ReviewStatus.IN_PROGRESS, ReviewStatus.RECTIFYING])
    db = mgr._get_session()
    row = db.query(ReviewSession).filter(ReviewSession.id == rs["id"]).first()
    row.file_ids = ["fake-file"]
    db.commit()
    mgr._close_session(db)

    monkeypatch.setattr(recheck_mod, "run_findings_for_file", lambda fid, bt="civil": [dict(F_A), dict(F_B)])
    result, msg = recheck_mod.recheck_session(mgr, rs["id"], uid)
    assert result, msg
    # rechecking→rejected→rectifying→再复查（仅 F_A 仍在）
    _walk(mgr, rs["id"], uid, [ReviewStatus.REJECTED, ReviewStatus.RECTIFYING])
    monkeypatch.setattr(recheck_mod, "run_findings_for_file", lambda fid, bt="civil": [dict(F_A)])
    result2, msg = recheck_mod.recheck_session(mgr, rs["id"], uid)
    assert result2, msg
    cmp = result2["comparison"]
    assert cmp["resolved"]["count"] == 1 and cmp["persisted"]["count"] == 1 and cmp["new"]["count"] == 0
    assert cmp["resolved"]["items"][0]["func_id"] == "F2"


def test_recheck_new_findings(mgr, monkeypatch):
    """复查发现新增违规：new 计数与明细正确。"""
    uid, rs = _make_session(mgr)
    _walk(mgr, rs["id"], uid, [ReviewStatus.PENDING, ReviewStatus.IN_PROGRESS, ReviewStatus.RECTIFYING])
    db = mgr._get_session()
    row = db.query(ReviewSession).filter(ReviewSession.id == rs["id"]).first()
    row.file_ids = ["fake-file"]
    db.commit()
    mgr._close_session(db)

    monkeypatch.setattr(recheck_mod, "run_findings_for_file", lambda fid, bt="civil": [dict(F_A)])
    result, _ = recheck_mod.recheck_session(mgr, rs["id"], uid)
    assert result
    _walk(mgr, rs["id"], uid, [ReviewStatus.REJECTED, ReviewStatus.RECTIFYING])
    monkeypatch.setattr(recheck_mod, "run_findings_for_file", lambda fid, bt="civil": [dict(F_A), dict(F_C)])
    result2, msg = recheck_mod.recheck_session(mgr, rs["id"], uid)
    assert result2, msg
    cmp = result2["comparison"]
    assert cmp["new"]["count"] == 1 and cmp["new"]["items"][0]["func_id"] == "F3"
    assert cmp["persisted"]["count"] == 1


def test_recheck_illegal_state(mgr, monkeypatch):
    """非 rectifying/rechecking 可达状态复查被拒（draft 起步）。"""
    uid, rs = _make_session(mgr)
    db = mgr._get_session()
    row = db.query(ReviewSession).filter(ReviewSession.id == rs["id"]).first()
    row.file_ids = ["fake-file"]
    db.commit()
    mgr._close_session(db)
    monkeypatch.setattr(recheck_mod, "run_findings_for_file", lambda fid, bt="civil": [dict(F_A)])
    result, msg = recheck_mod.recheck_session(mgr, rs["id"], uid)
    assert result is None
    assert "非法状态流转" in msg
    assert mgr.get_review_session(rs["id"], uid)["status"] == ReviewStatus.DRAFT.value


def test_recheck_no_files(mgr):
    """未关联图纸的会话复查报错。"""
    uid, rs = _make_session(mgr)
    _walk(mgr, rs["id"], uid, [ReviewStatus.PENDING, ReviewStatus.IN_PROGRESS, ReviewStatus.RECTIFYING])
    result, msg = recheck_mod.recheck_session(mgr, rs["id"], uid)
    assert result is None
    assert "会话未关联图纸文件" in msg


def test_recheck_permission_and_missing_file(mgr, monkeypatch):
    """无权限拒绝；文件复跑失败全部报错时复查失败。"""
    uid, rs = _make_session(mgr)
    other, msg = mgr.register_user("outsider2", "pass123456")
    assert other, msg
    _walk(mgr, rs["id"], uid, [ReviewStatus.PENDING, ReviewStatus.IN_PROGRESS, ReviewStatus.RECTIFYING])
    result, msg = recheck_mod.recheck_session(mgr, rs["id"], other["id"])
    assert result is None and msg == "无权限"

    db = mgr._get_session()
    row = db.query(ReviewSession).filter(ReviewSession.id == rs["id"]).first()
    row.file_ids = ["ghost-file"]
    db.commit()
    mgr._close_session(db)

    def _raise(fid, bt="civil"):
        raise FileNotFoundError(fid)

    monkeypatch.setattr(recheck_mod, "run_findings_for_file", _raise)
    result, msg = recheck_mod.recheck_session(mgr, rs["id"], uid)
    assert result is None
    assert "复查失败" in msg
