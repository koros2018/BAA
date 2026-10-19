# -*- coding: utf-8 -*-
"""拓扑 API 测试（T-B1 / B1b）。"""

from fastapi.testclient import TestClient

from src.api.baa_api import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer test-api-key"}

ENTITIES = [
    {"id": "r1", "type": "room", "bbox": {"x": 0, "y": 0, "width": 5000, "height": 4000}},
    {"id": "r2", "type": "room", "bbox": {"x": 5200, "y": 0, "width": 5000, "height": 4000}},
    {"id": "d1", "type": "door", "bbox": {"x": 4000, "y": 1500, "width": 900, "height": 200}},
    {"id": "bad", "type": "wall"},  # 缺 bbox → 应被过滤
]


class TestTopologyEndpoint:
    def test_post_topology_ok(self):
        r = client.post("/api/v1/topology", json={"entities": ENTITIES}, headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["input_count"] == 4
        assert data["consumed_count"] == 3
        assert data["room_count"] == 2
        assert data["edge_count"] == 2  # r1-r2 adjacent + d1-r1 contains
        assert data["is_connected"] is True

    def test_post_topology_empty(self):
        r = client.post("/api/v1/topology", json={"entities": []}, headers=AUTH)
        assert r.status_code == 200
        assert r.json()["node_count"] == 0

    def test_post_topology_invalid_body(self):
        r = client.post("/api/v1/topology", json={"wrong": 1}, headers=AUTH)
        assert r.status_code == 200
        assert r.json()["status"] == "error"
        assert "entities" in r.json()["error"]
