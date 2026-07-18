"""
Review routes 核心路径测试
覆盖：deconstruct 端点核心逻辑
"""

import sys
import os
import json
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient
from src.api.baa_api import app, API_KEYS

client = TestClient(app)

# 设置测试 Key
os.environ["BAA_API_KEY"] = "test-review-key"
API_KEYS.add("test-review-key")

# ── 共享测试数据 ──

SAMPLE_ENTITIES = [
    {"id": "door_001", "type": "door", "layer": "E-DOOR",
     "bbox": {"x": 0, "y": 0, "width": 0.9, "height": 2.1},
     "width": 0.9, "height": 2.1, "center": [0.45, 1.05], "attributes": {"防火": True}},
    {"id": "wall_001", "type": "wall", "layer": "E-WALL",
     "bbox": {"x": 0, "y": 0, "width": 10.0, "height": 0.2},
     "width": 10.0, "height": 0.2, "center": [5.0, 0.1], "attributes": {"耐火": "2h"}},
    {"id": "stair_001", "type": "staircase", "layer": "E-STRS",
     "bbox": {"x": 5.0, "y": 5.0, "width": 3.0, "height": 4.0},
     "width": 3.0, "height": 4.0, "center": [6.5, 7.0], "attributes": {}},
    {"id": "exit_001", "type": "exit", "layer": "E-DOOR",
     "bbox": {"x": 8.0, "y": 2.0, "width": 1.2, "height": 2.4},
     "width": 1.2, "height": 2.4, "center": [8.6, 3.2], "attributes": {"安全出口": True}},
    {"id": "room_001", "type": "room", "layer": "E-ROOM",
     "bbox": {"x": 0, "y": 0, "width": 10.0, "height": 8.0},
     "width": 10.0, "height": 8.0, "center": [5.0, 4.0], "attributes": {"名称": "办公室", "面积": 80.0}},
]


def _make_mock_parse_result(success=True):
    result = MagicMock()
    result.success = success
    result.error = None
    result.primitives = []
    result.dimensions = []
    return result


def _make_mock_func_registry(entities):
    """创建一个 mock FuncRegistry 避免 260 原子函数真实执行"""
    registry = MagicMock()
    # list_all 返回空列表 = 无检查，跳过 Step 3 规范判定
    registry.list_all = MagicMock(return_value=[])
    registry.count = 0
    return registry


def _make_mock_attr_analyzer():
    analyzer = MagicMock()
    analyzer.build_finding = MagicMock(return_value=MagicMock(
        finding_id="test-001",
        explanation="test explanation",
    ))
    return analyzer


# ── 测试 1: 未认证请求 ──


def test_deconstruct_unauthorized():
    """未认证请求应返回 401/403"""
    response = client.post("/deconstruct")
    assert response.status_code in (401, 403, 422)


# ── 测试 2: 不支持的格式 ──


def test_deconstruct_unsupported_format():
    """不支持的文件格式应返回 400"""
    response = client.post(
        "/deconstruct",
        files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
        headers={"Authorization": "Bearer test-review-key"},
    )
    # 格式校验在 auth 之后执行，所以需要带 auth
    assert response.status_code == 400, f"expected 400 got {response.status_code}: {response.text}"
    data = response.json()
    assert "UNSUPPORTED_FORMAT" in str(data)


# ── 测试 3: 大文件拒绝 ──


def test_deconstruct_file_too_large():
    """超大文件应返回 400"""
    big_content = b"x" * (51 * 1024 * 1024)  # 51MB
    response = client.post(
        "/deconstruct",
        files={"file": ("big.dxf", big_content, "application/dxf")},
        headers={"Authorization": "Bearer test-review-key"},
    )
    assert response.status_code == 400
    data = response.json()
    assert "FILE_TOO_LARGE" in str(data)


# ── 测试 4: deconstruct 返回 entities（完全 mock 引擎）──


def test_deconstruct_returns_entities():
    """deconstruct 端点应返回 entities 字段（fix: 045efbf）"""
    entities = SAMPLE_ENTITIES.copy()
    parse_result = _make_mock_parse_result()
    func_registry = _make_mock_func_registry(entities)
    attr_analyzer = _make_mock_attr_analyzer()

    with patch("src.api.baa_api._drawing_parser") as mock_dp, \
         patch("src.api.baa_api._semantic_analyzer") as mock_sa:

        # 直接 patch 模块级变量
        import src.api.baa_api as baa_api
        baa_api._func_registry = func_registry
        baa_api._attribution_analyzer = attr_analyzer

        mock_dp.parse = MagicMock(return_value=parse_result)
        mock_sa.analyze = MagicMock(return_value={
            "entities": entities, "relations": [],
        })

        async def mock_run_in_executor(self, executor, func, *args):
            return func(*args)

        with patch.object(asyncio.BaseEventLoop, "run_in_executor", mock_run_in_executor):
            response = client.post(
                "/deconstruct",
                files={"file": ("test.dxf", b"mock dxf content", "application/dxf")},
                headers={"Authorization": "Bearer test-review-key"},
            )

    assert response.status_code == 200, f"deconstruct failed: {response.text}"
    data = response.json()
    assert "entities" in data, "deconstruct 应返回 entities 字段"
    assert len(data["entities"]) == len(SAMPLE_ENTITIES)
    assert "summary" in data


# ── 测试 5: deconstruct JSON 序列化（numpy 兼容）──


def test_deconstruct_json_serializable():
    """deconstruct 返回应可 JSON 序列化（fix: 045efbf numpy 类型）"""
    import numpy as np

    entities_with_numpy = [
        {"id": "numpy_test", "type": "door", "layer": "E-DOOR",
         "bbox": {"x": np.float64(0.0), "y": np.float64(0.0), "width": np.float64(1.0), "height": np.float64(2.0)},
         "width": np.float32(0.9), "height": np.float32(2.1),
         "center": [np.float64(0.45), np.float64(1.05)],
         "attributes": {"flag": np.bool_(True), "count": np.int32(5)}},
    ]

    parse_result = _make_mock_parse_result()
    func_registry = _make_mock_func_registry(entities_with_numpy)
    attr_analyzer = _make_mock_attr_analyzer()

    with patch("src.api.baa_api._drawing_parser") as mock_dp, \
         patch("src.api.baa_api._semantic_analyzer") as mock_sa:

        import src.api.baa_api as baa_api
        baa_api._func_registry = func_registry
        baa_api._attribution_analyzer = attr_analyzer

        mock_dp.parse = MagicMock(return_value=parse_result)
        mock_sa.analyze = MagicMock(return_value={
            "entities": entities_with_numpy, "relations": [],
        })

        async def mock_run_in_executor(self, executor, func, *args):
            return func(*args)

        with patch.object(asyncio.BaseEventLoop, "run_in_executor", mock_run_in_executor):
            response = client.post(
                "/deconstruct",
                files={"file": ("test.dxf", b"mock dxf content", "application/dxf")},
                headers={"Authorization": "Bearer test-review-key"},
            )

    assert response.status_code == 200, f"numpy serialization failed: {response.text}"
    data = response.json()
    # 验证 JSON 序列化不会报错
    dumped = json.dumps(data)
    assert len(dumped) > 0
    # numpy 类型应被转换为原生 Python 类型
    assert isinstance(data["entities"][0]["width"], (int, float))
    assert isinstance(data["entities"][0]["attributes"]["flag"], bool)


# ── 测试 6: review-pdf 端点 ──


def test_review_pdf_not_found():
    """不存在的 review 记录应返回 404"""
    response = client.get(
        "/review/nonexistent-file/pdf",
        headers={"Authorization": "Bearer test-review-key"},
    )
    assert response.status_code == 404


# ── 测试 7: review-from-data 端点 ──


def test_review_from_data_accepts_json():
    """review-from-data 应接受实体 JSON"""
    with patch("src.api.review_routes._get_fr") as mock_fr, \
         patch("src.api.review_routes._get_sr") as mock_sr:
        mock_sr.return_value.get_relevant_functions = MagicMock(
            return_value=lambda: []
        )
        response = client.post(
            "/review-from-data",
            json={"entities": SAMPLE_ENTITIES},
            headers={"Authorization": "Bearer test-review-key"},
        )
    assert response.status_code in (200, 503), \
        f"review-from-data failed: {response.status_code}: {response.text}"


# ── 测试 8: review 未认证 ──


def test_review_unauthorized():
    """review 未认证应返回 401/403"""
    response = client.post("/review")
    assert response.status_code in (401, 403, 422)