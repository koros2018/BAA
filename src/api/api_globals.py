"""
API 共享全局变量与工具函数

用于 baa_api.py 和各子路由模块（collab_routes.py, admin_routes.py 等）
之间共享状态，避免循环依赖。
"""

from __future__ import annotations  # noqa: F401
import os
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Set
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException, Request, Header, Query, Depends

# ── 项目路径 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # src/../
import sys

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = Path(os.getenv("BAA_DATA_DIR", str(PROJECT_ROOT / "data")))
FILES_DIR = DATA_DIR / "files"
MODELS_DIR = DATA_DIR / "models"
DATA_DIR.mkdir(parents=True, exist_ok=True)
FILES_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# ── 异步任务存储 ──────────────────────────────────────────
_tasks: Dict[str, dict] = {}
_webhooks: Dict[str, dict] = {}

# ── 审查结果缓存 ──────────────────────────────────────────
from src.baa_engine.cache import get_cache

_persistent_cache = get_cache()
_review_cache: Dict[str, dict] = {}
_REVIEW_CACHE_MAX = 100

# ── 文件格式与大小限制 ──────────────────────────────────
SUPPORTED_FORMATS: Set[str] = {"dxf", "dwg"}
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

# ── API 密钥 ──────────────────────────────────────────────
API_KEYS: Set[str] = set()
_api_key = os.getenv("BAA_API_KEY", "")
if _api_key:
    API_KEYS.add(_api_key)

# ── 认证密钥 ──────────────────────────────────────────────
AUTH_SECRETS: List[str] = [
    s.strip() for s in os.getenv("BAA_AUTH_SECRET", "").split(",") if s.strip()
]
if not AUTH_SECRETS:
    AUTH_SECRETS = ["baa-dev-secret-change-in-production"]

# ── 线程池 ────────────────────────────────────────────────
ENGINE_THREAD_POOL = ThreadPoolExecutor(
    max_workers=min(8, (os.cpu_count() or 4) * 2),
    thread_name_prefix="baa-engine",
)

# ── 引擎引用（由 lifespan 预热加载） ──────────────────────
_drawing_parser = None
_semantic_analyzer = None
_func_registry = None
_attribution_analyzer = None
_spec_repo = None
_feedback_manager: Optional["FeedbackManager"] = None
_learning_engine: Optional["LearningEngine"] = None


def get_key_manager():
    """获取 API 密钥管理器（懒加载）"""
    from src.baa_engine.api_key_manager import get_key_manager as _get_km

    return _get_km()


def generate_file_id() -> str:
    """生成唯一文件标识符"""
    return f"baa-file-{uuid.uuid4().hex[:12]}"


def store_file(content: bytes, file_id: str, extension: str) -> Path:
    """保存上传文件到磁盘"""
    path = FILES_DIR / f"{file_id}.{extension}"
    path.write_bytes(content)
    return path


def get_file_path(file_id: str) -> Optional[Path]:
    """根据文件 ID 查找已存储的图纸文件"""
    for ext in SUPPORTED_FORMATS:
        path = FILES_DIR / f"{file_id}.{ext}"
        if path.exists():
            return path
    return None


def extract_api_key(
    authorization: str = Header("", description="Bearer API Key"),
    api_key: str = Query("", description="API Key (alternative to Bearer header)"),
) -> str:
    """从 Authorization Header 或 Query 参数中提取 API Key

    优先使用 Authorization: Bearer <key> 格式的 Header。
    Query 参数 ?api_key=xxx 作为 fallback（兼容 Swagger UI 调试）。
    """
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    return api_key


def verify_api_key(api_key: str = Depends(extract_api_key)) -> str:
    """验证 API 密钥（含提取 + 校验）"""
    if not API_KEYS:
        return "anonymous"
    if api_key and api_key in API_KEYS:
        return api_key
    km = get_key_manager()
    key_info = km.validate_key(api_key)
    if key_info and key_info.get("enabled", True):
        return api_key
    raise HTTPException(
        status_code=401,
        detail={
            "status": "error",
            "error_code": "UNAUTHORIZED",
            "message": "无效的API Key",
        },
    )


def require_admin(request: Request, api_key: str = "") -> str:
    """验证 admin 权限"""
    if not API_KEYS:
        return "anonymous"
    km = get_key_manager()
    key_info = km.validate_key(api_key)
    if key_info and key_info.get("permission") == "admin":
        return api_key
    if api_key and api_key in API_KEYS:
        return api_key
    raise HTTPException(
        status_code=403,
        detail={
            "status": "error",
            "error_code": "FORBIDDEN",
            "message": "需要admin权限",
        },
    )
# ── 审查任务队列 ──────────────────────────────────────────
MAX_CONCURRENT_REVIEWS = 4
from src.baa_engine.task_queue import ReviewQueue  # noqa: E402

_review_queue = ReviewQueue(max_concurrent=MAX_CONCURRENT_REVIEWS, queue_timeout=300.0)
_review_semaphore = None  # 兼容旧引用，由 baa_api.py 设置
