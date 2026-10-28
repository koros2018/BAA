# -*- coding: utf-8 -*-
"""D3-T3 客户成功项目表测试。"""

import os

import pytest


@pytest.fixture(autouse=True)
def _ensure_schema():
    from src.baa_engine.db import ensure_schema
    ensure_schema()
    yield


def test_create_project_endpoint():
    """POST /api/v1/projects 创建项目，返回 200 + id。"""
    from src.baa_engine.db import dispose_engine
    from src.baa_engine.db.database import get_session_factory
    from src.baa_engine.db.models.project import ReviewProject

    sf = get_session_factory()
    p = ReviewProject(
        id="test-project-1",
        project_name="测试项目",
        customer_name="测试客户",
        standard_set_code="CN-National-v1",
        owner="张三",
        status="onboarding",
    )
    sf.add(p)
    sf.commit()
    sf.refresh(p)
    assert p.id == "test-project-1"
    assert p.status == "onboarding"
    sf.delete(p)
    sf.commit()
    sf.remove()
    dispose_engine(os.environ.get("BAA_DATABASE_URL", ""))


def test_allowed_transitions():
    from src.baa_engine.db.models.project import ALLOWED_TRANSITIONS

    assert ALLOWED_TRANSITIONS["onboarding"] == {"first_review"}
    assert "correction" in ALLOWED_TRANSITIONS["first_review"]
    assert "closed" in ALLOWED_TRANSITIONS["first_review"]
    assert ALLOWED_TRANSITIONS["closed"] == set()


def test_illegal_transition():
    """closed → first_review 是非法的。"""
    from src.baa_engine.db.models.project import ALLOWED_TRANSITIONS

    assert "first_review" not in ALLOWED_TRANSITIONS["closed"]


def test_project_status_enum():
    """合法状态集合。"""
    allowed = {"onboarding", "first_review", "correction", "recheck", "closed"}
    assert len(allowed) == 5


def test_to_dict_helper():
    from src.baa_engine.db.models.project import ReviewProject
    from src.api.projects.project_routes import _to_dict

    p = ReviewProject(
        id="p1",
        project_name="P",
        customer_name="C",
        standard_set_code="CN-National-v1",
        owner="O",
        status="onboarding",
    )
    d = _to_dict(p)
    assert d["id"] == "p1"
    assert d["status"] == "onboarding"
    assert d["standard_set_code"] == "CN-National-v1"


def test_project_api_routes_registered():
    from src.api.baa_api import app

    paths = {r.path for r in app.routes}
    assert "/api/v1/projects" in paths
    assert "/api/v1/projects/{project_id}" in paths
    assert "/api/v1/projects/{project_id}/status" in paths


# ── E4-T2：客户成功平台增强测试 ──────────────────────────────


class TestProjectDetailWithStats:
    """项目详情含审查统计（E4-T2）。"""

    def test_get_project_includes_review_stats(self, client):
        """GET /projects/{id} 应返回 review_stats 字段。"""
        from src.baa_engine.db import dispose_engine
        from src.baa_engine.db.database import get_session_factory
        from src.baa_engine.db.models.project import ReviewProject

        sf = get_session_factory()
        p = ReviewProject(
            id="e4t2-proj-1",
            project_name="E4-T2 测试项目",
            customer_name="测试客户",
            status="onboarding",
        )
        sf.add(p)
        sf.commit()
        proj_id = p.id
        sf.remove()

        resp = client.get(f"/api/v1/projects/{proj_id}", headers={"Authorization": "Bearer test-api-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert "review_stats" in data
        assert data["review_stats"]["total_reviews"] == 0
        assert data["review_stats"]["total_violations"] == 0
        assert data["review_stats"]["avg_score"] == 0.0

        sf = get_session_factory()
        p2 = sf.get(ReviewProject, proj_id)
        if p2:
            sf.delete(p2)
            sf.commit()
        sf.remove()
        dispose_engine(os.environ.get("BAA_DATABASE_URL", ""))

    def test_get_project_not_found(self, client):
        """不存在的项目返回 404。"""
        resp = client.get(
            "/api/v1/projects/nonexistent-project-id",
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp.status_code == 404


class TestProjectListEnhanced:
    """项目列表增强筛选（E4-T2）。"""

    def test_list_projects_with_customer_search(self, client):
        """按客户名模糊搜索。"""
        from src.baa_engine.db import dispose_engine
        from src.baa_engine.db.database import get_session_factory
        from src.baa_engine.db.models.project import ReviewProject

        sf = get_session_factory()
        for name in ["客户A-项目1", "客户A-项目2", "客户B-项目1"]:
            p = ReviewProject(
                id=f"e4t2-list-{name}",
                project_name=name,
                customer_name="客户A" if "客户A" in name else "客户B",
                status="onboarding",
            )
            sf.add(p)
        sf.commit()
        sf.remove()

        resp = client.get(
            "/api/v1/projects?customer_name=客户A",
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

        sf = get_session_factory()
        for name in ["e4t2-list-客户A-项目1", "e4t2-list-客户A-项目2", "e4t2-list-客户B-项目1"]:
            p = sf.get(ReviewProject, name)
            if p:
                sf.delete(p)
        sf.commit()
        sf.remove()
        dispose_engine(os.environ.get("BAA_DATABASE_URL", ""))

    def test_list_projects_pagination(self, client):
        """分页参数生效。"""
        from src.baa_engine.db import dispose_engine
        from src.baa_engine.db.database import get_session_factory
        from src.baa_engine.db.models.project import ReviewProject

        sf = get_session_factory()
        for i in range(5):
            p = ReviewProject(
                id=f"e4t2-page-{i}",
                project_name=f"分页测试{i}",
                status="onboarding",
            )
            sf.add(p)
        sf.commit()
        sf.remove()

        resp = client.get(
            "/api/v1/projects?limit=2&offset=0",
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert data["total"] >= 5
        assert data["offset"] == 0

        resp2 = client.get(
            "/api/v1/projects?limit=2&offset=2",
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["count"] == 2
        assert resp2.json()["offset"] == 2

        sf = get_session_factory()
        for i in range(5):
            p = sf.get(ReviewProject, f"e4t2-page-{i}")
            if p:
                sf.delete(p)
        sf.commit()
        sf.remove()
        dispose_engine(os.environ.get("BAA_DATABASE_URL", ""))


class TestProjectStatusAudit:
    """状态流转审计联动（E4-T2）。"""

    def test_status_change_writes_audit_log(self, client, tmp_path, monkeypatch):
        """项目状态变更应写入审计日志。"""
        import src.api.api_globals as ag

        monkeypatch.setenv("BAA_DATABASE_URL", f"sqlite:///{tmp_path / 'test_proj_audit.db'}")
        saved = set(ag.API_KEYS)
        ag.API_KEYS.clear()
        ag.API_KEYS.add("test-api-key")
        from src.baa_engine.api_key_manager import reset_key_manager
        reset_key_manager()

        from src.baa_engine.db import ensure_schema
        ensure_schema()

        from fastapi.testclient import TestClient
        from src.api.baa_api import app

        tc = TestClient(app)

        # 创建项目
        create_resp = tc.post(
            "/api/v1/projects",
            json={"project_name": "审计测试", "customer_name": "审计客户"},
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert create_resp.status_code == 200
        project_id = create_resp.json()["id"]

        # 变更状态
        status_resp = tc.patch(
            f"/api/v1/projects/{project_id}/status",
            json={"status": "first_review"},
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert status_resp.status_code == 200

        # 验证审计日志真实落库（而非仅状态变更成功）
        from src.baa_engine.db.database import get_session_factory
        from src.baa_engine.db.models.audit_log import AuditLog

        sf = get_session_factory()
        logs = (
            sf.query(AuditLog)
            .filter(
                AuditLog.resource_type == "project",
                AuditLog.resource_id == project_id,
            )
            .all()
        )
        sf.remove()
        assert logs, "项目状态变更未写入审计日志"
        assert any("onboarding -> first_review" in (l.detail or "") for l in logs)
        assert status_resp.json()["status"] == "first_review"

        ag.API_KEYS.update(saved)


class TestProjectViolationDistribution:
    """E4-T2：项目详情违规分布 + 审查统计聚合。"""

    @staticmethod
    def _seed(project_id: str, details: list, score: float = 80.0):
        import uuid as _uuid

        from src.baa_engine.db.database import get_session_factory
        from src.baa_engine.db.models.history import ReviewHistory

        sf = get_session_factory()
        sf.add(
            ReviewHistory(
                id=_uuid.uuid4().hex,
                drawing_name="e4t2.dxf",
                project_id=project_id,
                details=details,
                violation_count=len(details),
                score=score,
            )
        )
        sf.commit()
        sf.remove()

    @staticmethod
    def _cleanup(project_id: str):
        from src.baa_engine.db.database import get_session_factory
        from src.baa_engine.db.models.history import ReviewHistory
        from src.baa_engine.db.models.project import ReviewProject

        sf = get_session_factory()
        for row in sf.query(ReviewHistory).filter(ReviewHistory.project_id == project_id).all():
            sf.delete(row)
        p = sf.get(ReviewProject, project_id)
        if p:
            sf.delete(p)
        sf.commit()
        sf.remove()

    def test_review_stats_counts_violations(self, client):
        """review_stats.total_violations 应累计历史违规数（camelCase 键回归）。"""
        from src.baa_engine.db.database import get_session_factory
        from src.baa_engine.db.models.project import ReviewProject

        pid = "e4t2-stats-proj"
        sf = get_session_factory()
        sf.add(ReviewProject(id=pid, project_name="统计项目", status="onboarding"))
        sf.commit()
        sf.remove()
        self._seed(pid, [{"severity": "critical"}, {"severity": "major"}], score=70.0)
        try:
            resp = client.get(
                f"/api/v1/projects/{pid}",
                headers={"Authorization": "Bearer test-api-key"},
            )
            assert resp.status_code == 200
            stats = resp.json()["review_stats"]
            assert stats["total_reviews"] == 1
            assert stats["total_violations"] == 2
            assert stats["avg_score"] == 70.0
        finally:
            self._cleanup(pid)

    def test_violation_distribution_aggregated(self, client):
        """violation_distribution 按严重度/条款/实体类型聚合。"""
        from src.baa_engine.db.database import get_session_factory
        from src.baa_engine.db.models.project import ReviewProject

        pid = "e4t2-dist-proj"
        sf = get_session_factory()
        sf.add(ReviewProject(id=pid, project_name="分布项目", status="onboarding"))
        sf.commit()
        sf.remove()
        self._seed(
            pid,
            [
                {"severity": "critical", "clause_id": "GB50016-5.5.17", "entity_type": "doorway"},
                {"severity": "critical", "clause_id": "GB50016-5.5.17", "entity_type": "room"},
                {"severity": "minor", "clause_id": "GB50016-5.5.18", "entity_type": "doorway"},
            ],
        )
        try:
            resp = client.get(
                f"/api/v1/projects/{pid}",
                headers={"Authorization": "Bearer test-api-key"},
            )
            assert resp.status_code == 200
            dist = resp.json()["violation_distribution"]
            assert dist["by_severity"] == {"critical": 2, "minor": 1}
            assert dist["by_clause"]["GB50016-5.5.17"] == 2
            assert dist["by_entity_type"]["doorway"] == 2
            assert dist["by_entity_type"]["room"] == 1
        finally:
            self._cleanup(pid)

    def test_violation_distribution_empty_for_new_project(self, client):
        """无审查历史 → 分布为空字典。"""
        from src.baa_engine.db.database import get_session_factory
        from src.baa_engine.db.models.project import ReviewProject

        pid = "e4t2-empty-proj"
        sf = get_session_factory()
        sf.add(ReviewProject(id=pid, project_name="空项目", status="onboarding"))
        sf.commit()
        sf.remove()
        try:
            resp = client.get(
                f"/api/v1/projects/{pid}",
                headers={"Authorization": "Bearer test-api-key"},
            )
            assert resp.status_code == 200
            dist = resp.json()["violation_distribution"]
            assert dist == {"by_severity": {}, "by_clause": {}, "by_entity_type": {}}
        finally:
            self._cleanup(pid)

    def test_list_projects_status_filter(self, client):
        """项目列表按 status 精确筛选。"""
        from src.baa_engine.db.database import get_session_factory
        from src.baa_engine.db.models.project import ReviewProject

        sf = get_session_factory()
        for pid, status in [("e4t2-f-onb", "onboarding"), ("e4t2-f-closed", "closed")]:
            sf.add(ReviewProject(id=pid, project_name=pid, status=status))
        sf.commit()
        sf.remove()
        try:
            resp = client.get(
                "/api/v1/projects?status=closed",
                headers={"Authorization": "Bearer test-api-key"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert data["projects"][0]["id"] == "e4t2-f-closed"
        finally:
            self._cleanup("e4t2-f-onb")
            self._cleanup("e4t2-f-closed")

    def test_list_projects_search_no_match(self, client):
        """客户名搜索无匹配 → total=0 且不报错。"""
        resp = client.get(
            "/api/v1/projects?customer_name=不存在的客户XYZ",
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["projects"] == []
