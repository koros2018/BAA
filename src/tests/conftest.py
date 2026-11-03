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

# ── T-C1：统一数据层测试隔离（必须在 import baa_api 之前生效） ─────────
# 每个 pytest 进程/xdist worker 使用独立 SQLite 文件 + 独立上传目录：
# ① 不污染真实 data/ 目录 ② 规避共享文件锁竞争 ③ 显式设置过的 BAA_DATABASE_URL 不覆盖
import atexit  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

_TEST_DB = Path(tempfile.gettempdir()) / f"baa_test_{os.getpid()}.db"
os.environ.setdefault("BAA_DATABASE_URL", f"sqlite:///{_TEST_DB.as_posix()}")

# P0-3：测试上传文件写入独立临时目录，避免污染 data/files/
# api_globals 在模块导入时读取 BAA_DATA_DIR 初始化 FILES_DIR；
# 覆盖后还需刷新已导入的 src.api.api_globals 模块的全局变量
_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="baa_test_data_"))


def _cleanup_test_data_dir():
    """进程退出：清除测试上传目录（baa-file-*.dxf 等桩文件）。"""
    try:
        import shutil

        shutil.rmtree(str(_TEST_DATA_DIR), ignore_errors=True)
    except Exception:
        pass


atexit.register(_cleanup_test_data_dir)


def _cleanup_test_db():
    """进程退出：先释放全部引擎连接（否则池化连接锁定 SQLite 文件），再删临时库。"""
    from src.baa_engine.db import dispose_all

    try:
        dispose_all()
    except Exception:
        pass
    Path(str(_TEST_DB)).unlink(missing_ok=True)


atexit.register(_cleanup_test_db)

# ── P0-3：隔离测试上传目录（必须在 import baa_api 之前生效） ──────────
# api_globals.py 在模块导入时读取 BAA_DATA_DIR 初始化 FILES_DIR；
# 覆盖环境变量后刷新已导入的 src.api.api_globals 模块的全局变量
os.environ["BAA_DATA_DIR"] = str(_TEST_DATA_DIR)

from fastapi.testclient import TestClient  # noqa: E402
from src.api.baa_api import app  # noqa: E402

# 刷新 api_globals 的 FILES_DIR（使其指向测试临时目录而非 data/files）
import src.api.api_globals as _ag

_ag.DATA_DIR = _TEST_DATA_DIR
_ag.FILES_DIR = _TEST_DATA_DIR / "files"
_ag.FILES_DIR.mkdir(parents=True, exist_ok=True)


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
