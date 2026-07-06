"""pytest 配置：确保项目路径在 sys.path 中，asyncio 测试模式"""

import sys  # import
import os  # stdlib: filesystem ops

# 项目根目录
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # path operation
if PROJECT_ROOT not in sys.path:  # check: membership test
    sys.path.insert(0, PROJECT_ROOT)  # sys path


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
