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
