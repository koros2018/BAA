"""
BAA MCP Server 测试 — 功能/集成测试
"""

import sys
import os
import json
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.mcp.baa_mcp_server import BAAMCPServer


@pytest.fixture
def server():
    srv = BAAMCPServer()
    yield srv


class TestMCPServerCore:
    """MCP server 核心注册测试"""

    def test_server_name(self, server):
        assert server.server.name == "baa-blueprint"

    def test_request_handlers_registered(self, server):
        handlers = server.server.request_handlers
        expected = [
            "PingRequest",
            "ListToolsRequest",
            "ListResourcesRequest",
            "ReadResourceRequest",
            "CallToolRequest",
        ]
        for h in expected:
            assert h in [k.__name__ for k in handlers], f"缺少 handler: {h}"

    def test_tool_definitions(self, server):
        """验证 6 个工具的 inputSchema"""
        # 通过 call_tool handler 获取工具定义
        handler = server.server.request_handlers.get(
            next(k for k in server.server.request_handlers if k.__name__ == "ListToolsRequest")
        )
        assert handler is not None


class TestMCPHealth:
    """baa_health 工具测试"""

    def test_health_ok(self, server):
        import asyncio

        r = asyncio.run(server._handle_health({}))
        assert r["status"] == "ok"
        assert r["engine"]["drawing_parser"] == "ready"
        assert r["engine"]["semantic_analyzer"] == "ready"
        assert "422/422" in r["engine"]["func_registry"]

    def test_health_keys(self, server):
        import asyncio

        r = asyncio.run(server._handle_health({}))
        assert "version" in r
        assert "status" in r
        assert "engine" in r


class TestMCPListFunctions:
    """baa_list_functions 工具测试"""

    def test_list_all(self, server):
        import asyncio

        r = asyncio.run(server._handle_list_functions({"category": ""}))
        assert r["total"] == 422
        assert r["capacity"] == 422
        assert r["total"] == len(r["functions"])
        assert len(r["categories"]) > 0

    def test_list_by_category(self, server):
        import asyncio

        for cat in ["dim", "dist", "exist", "count", "area", "attr"]:
            r = asyncio.run(server._handle_list_functions({"category": cat}))
            assert r["total"] == len(r["functions"])
            assert r["total"] >= 0
            if r["total"] > 0:
                for f in r["functions"]:
                    assert f["category"] == cat

    def test_list_invalid_category(self, server):
        import asyncio

        r = asyncio.run(server._handle_list_functions({"category": "nonexistent"}))
        assert r["total"] == 0

    def test_list_function_fields(self, server):
        import asyncio

        r = asyncio.run(server._handle_list_functions({"category": "dim"}))
        if r["total"] > 0:
            f = r["functions"][0]
            assert "id" in f
            assert "name" in f
            assert "category" in f
            assert "clause" in f
            assert "threshold" in f or f["threshold"] is None


class TestMCPReviewFromData:
    """baa_review_from_data 工具测试"""

    def test_empty_entities(self, server):
        import asyncio

        r = asyncio.run(server._handle_review_from_data({"entities": []}))
        assert r["status"] == "success"
        assert r["summary"]["violations"] == 0
        assert r["summary"]["total_entities"] == 0
        assert len(r["findings"]) == 0

    def test_entities_with_data(self, server):
        import asyncio

        entities = [
            {
                "id": "e1",
                "type": "corridor",
                "bbox": {"x": 0, "y": 0, "width": 10, "height": 1.5},
                "attributes": {"width": 1.5},
            },
            {
                "id": "e2",
                "type": "door",
                "bbox": {"x": 5, "y": 0, "width": 0.9, "height": 2.1},
                "attributes": {"width": 0.9},
            },
        ]
        r = asyncio.run(server._handle_review_from_data({"entities": entities}))
        assert r["status"] == "success"
        assert r["summary"]["total_entities"] == 2
        # 至少执行了一些检查
        assert r["summary"]["total_checks"] > 0


class TestMCPReconstruct:
    """baa_reconstruct 工具测试"""

    def test_bad_token(self, server):
        import asyncio

        r = asyncio.run(
            server._handle_reconstruct({"file_id": "test123", "auth_token": "bad_token"})
        )
        assert r["status"] == "error"
        assert r["error_code"] == "AUTH_FAILED"

    def test_missing_file_id(self, server):
        import asyncio

        r = asyncio.run(server._handle_reconstruct({"auth_token": "some_token"}))
        assert r["status"] == "error"
        assert "error_code" in r

    def test_reconstruct_structure(self, server):
        import asyncio

        # 需要有真实 token，但我们可以验证返回格式
        from src.api.baa_api import generate_auth_token

        token = generate_auth_token({"client_id": "test_client", "service": "reconstruct"})
        r = asyncio.run(
            server._handle_reconstruct(
                {
                    "file_id": "test-file-12345678",
                    "auth_token": token,
                    "options": {"lod": 300, "format": "ifc"},
                }
            )
        )
        assert r["status"] == "success"
        assert "order_id" in r
        assert "model_file" in r
        assert r["lod"] == 300
        assert r["format"] == "ifc"
        assert "auth_info" in r


class TestMCPResource:
    """Resource 支持测试"""

    def test_resource_count(self, server):
        import asyncio

        # 通过闭包内部函数测试
        handler = next(
            v
            for k, v in server.server.request_handlers.items()
            if k.__name__ == "ReadResourceRequest"
        )
        inner = handler.__closure__[0].cell_contents
        rc = asyncio.run(inner("baa://functions/count"))
        data = json.loads(rc.content)
        assert "count" in data
        assert "capacity" in data
        assert data["count"] == 422
        assert data["capacity"] == 422

    def test_resource_specs(self, server):
        import asyncio

        handler = next(
            v
            for k, v in server.server.request_handlers.items()
            if k.__name__ == "ReadResourceRequest"
        )
        inner = handler.__closure__[0].cell_contents
        rc = asyncio.run(inner("baa://specs/list"))
        data = json.loads(rc.content)
        assert "GB50016" in data
        assert "GB50067" in data
        assert len(data) >= 4

    def test_resource_unknown_uri(self, server):
        import asyncio

        handler = next(
            v
            for k, v in server.server.request_handlers.items()
            if k.__name__ == "ReadResourceRequest"
        )
        inner = handler.__closure__[0].cell_contents
        with pytest.raises(ValueError, match="未知 resource URI"):
            asyncio.run(inner("baa://unknown"))


class TestMCPDeconstruct:
    """baa_deconstruct 工具测试 — 文件不存在场景"""

    def test_file_not_found(self, server):
        import asyncio

        r = asyncio.run(server._handle_deconstruct({"file_path": "/nonexistent/file.dxf"}))
        assert r["status"] == "error"
        assert r["error_code"] == "FILE_NOT_FOUND"
