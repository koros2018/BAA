"""pytest 配置：确保项目路径在 sys.path 中，asyncio 测试模式 + 全局 client"""

import sys  # import
import os  # stdlib: filesystem ops
import pytest

# 项目根目录
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # path operation
if PROJECT_ROOT not in sys.path:  # check: membership test
    sys.path.insert(0, PROJECT_ROOT)  # sys path

# ── 全局 client fixture（所有测试文件可用） ─────────
os.environ["BAA_API_KEY"] = "test-api-key"
os.environ["BAA_AUTH_SECRET"] = "test-secret"
from fastapi.testclient import TestClient
from src.api.baa_api import app


@pytest.fixture(scope="module")
def client():
    """全局 TestClient，供 API 测试使用"""
    return TestClient(app)


def pytest_configure(config):  # function: pytest 配置钩子
    """注册自定义标记"""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async (uses pytest-asyncio)"  # 注册 asyncio 标记
    )  # function call
    config.addinivalue_line(
        "markers", "slow: slow-running tests (skip by default)"  # 注册 slow 标记
    )  # function call
    config.addinivalue_line(
        "markers", "api: API-level integration tests"  # 注册 api 标记
    )  # function call
