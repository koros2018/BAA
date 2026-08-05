"""P91: 审查结果结构化导出测试"""
import csv
import io
import time

from fastapi.testclient import TestClient

from src.api.baa_api import app
from src.api.review.review_history import save_review_result

client = TestClient(app)
_AUTH = {"Authorization": "Bearer test-api-key"}


def _make_review():
    rid = "test_p91_" + str(time.time()).replace(".", "")
    save_review_result(rid, "test.dxf", {
        "review_id": rid, "status": "success",
        "summary": {"total": 2, "fail_count": 1, "score": 50},
        "details": [
            {"clause_id": "DIM-001", "title": "疏散楼梯净宽", "severity": "critical",
             "status": "FAIL", "entity_id": "s1", "entity_type": "stair",
             "category": "evacuation", "current_value": "0.9", "required_value": "1.2",
             "delta": "-0.3", "confidence": "0.9", "description": "实测不足"},
            {"clause_id": "DIM-002", "title": "疏散门净宽", "severity": "major",
             "status": "PASS", "entity_id": "d1", "entity_type": "door",
             "category": "evacuation", "current_value": "1.0", "required_value": "0.9",
             "delta": "0.1", "confidence": "0.95", "description": "满足"},
        ],
        "corrections": [],
    })
    return rid


def test_json_format():
    rid = _make_review()
    r = client.get(f"/review/export?review_id={rid}&format=json", headers=_AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    data = r.json()
    assert data["summary"]["total"] == 2
    assert data["top_violations"][0]["severity"] == "critical"


def test_csv_format():
    rid = _make_review()
    r = client.get(f"/review/export?review_id={rid}&format=csv", headers=_AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text.lstrip("\ufeff"))))
    assert len(rows) == 3  # header + 2 data rows
    assert rows[0][0] == "clause_id"
    assert rows[1][0] == "DIM-001"


def test_csv_utf8_sig():
    """UTF-8 BOM 前缀确保 Excel 中文兼容"""
    rid = _make_review()
    r = client.get(f"/review/export?review_id={rid}&format=csv", headers=_AUTH)
    assert r.content.startswith(b"\xef\xbb\xbf")


def test_invalid_review_id():
    r = client.get("/review/export?review_id=nonexistent&format=json", headers=_AUTH)
    assert r.status_code == 404


def test_invalid_format():
    rid = _make_review()
    r = client.get(f"/review/export?review_id={rid}&format=xml", headers=_AUTH)
    assert r.status_code == 400
