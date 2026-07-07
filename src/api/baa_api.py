"""
BAA API 服务层 - FastAPI 实现

提供建筑图纸合规分析引擎的 REST API 接口，包括：
- /deconstruct: DWG/DXF 图纸拆解为结构化实体数据
- /reconstruct: 结构化数据重建为图纸
- /review: 图纸合规审查（核心功能）
- /order/{id}: 查询审查结果
- /health: 健康检查
- /admin/keys/*: API 密钥管理
- /api/v1/*: EMA2 第三方对接接口
- /api/v1/feedbacks/*: 用户反馈闭环
"""

# ── 标准库导入 ──────────────────────────────────────────────
import uuid  # 生成唯一标识符（文件ID、任务ID等）
import os  # 环境变量、路径操作
import time  # 时间戳、超时控制
import json  # JSON 序列化/反序列化
import gc  # 垃圾回收
from pathlib import Path  # 跨平台路径操作
from typing import Optional, List, Dict  # 类型注解
from datetime import datetime, timedelta  # 日期时间处理

# ── FastAPI 及依赖 ──────────────────────────────────────────
from fastapi import (
    FastAPI,
    File,
    UploadFile,
    HTTPException,
    Depends,
    Security,
    Query,
    Request,
    Response,
)  # fastapi: HTTP framework
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials  # import
from fastapi.middleware.cors import CORSMiddleware  # import
from fastapi.staticfiles import StaticFiles  # import

# ═══════════════════════════════════════════════════════════════
# 配置区
# ═══════════════════════════════════════════════════════════════

# ── 项目工作路径（默认：项目根目录下的 data/） ───────────

# 计算项目根目录（src/../）并加入 sys.path，确保模块可导入
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # src/../
import sys  # import

if str(PROJECT_ROOT) not in sys.path:  # check: membership test
    sys.path.insert(0, str(PROJECT_ROOT))  # sys path

# 数据目录：优先使用环境变量 BAA_DATA_DIR，否则默认为 data/
DATA_DIR = Path(os.getenv("BAA_DATA_DIR", str(PROJECT_ROOT / "data")))  # function call
FILES_DIR = DATA_DIR / "files"  # 上传的图纸文件存储目录
MODELS_DIR = DATA_DIR / "models"  # YOLO 模型文件目录
DATA_DIR.mkdir(parents=True, exist_ok=True)  # function call
FILES_DIR.mkdir(parents=True, exist_ok=True)  # function call
MODELS_DIR.mkdir(parents=True, exist_ok=True)  # function call

# ── 异步任务存储（内存） ───────────────────────────────────
from collections import Counter  # stdlib: collections
import hashlib  # stdlib: hashing

# EMA2 第三方对接用：异步审查任务 + Webhook 回调的全局存储
_tasks = {}  # task_id -> {status, result, created_at, webhook_url, ...}
_webhooks = {}  # webhook_id -> {url, events, active, ...}

# 审查结果缓存：持久化 SQLite 缓存（替代内存缓存）
from src.baa_engine.cache import get_cache, make_cache_key, PersistentCache  # import

_persistent_cache = get_cache()  # function call

# 保留内存缓存用于快速访问（二级缓存：内存→持久化）
_review_cache: Dict[str, dict] = {}  # assignment
_REVIEW_CACHE_MAX = 100  # assignment

# 支持的文件格式（DWG/DXF）
SUPPORTED_FORMATS = {"dxf", "dwg"}  # assignment
MAX_FILE_SIZE_MB = 50  # assignment
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024  # 上传文件大小上限（50MB）

# ── API 密钥（从环境变量加载） ────────────────────────────
API_KEYS = set()  # function call
_api_key = os.getenv("BAA_API_KEY", "")  # function call
if _api_key:  # condition: _api_key:
    API_KEYS.add(_api_key)  # function call

# ── 共享密钥（用于 auth_token 验证，支持多密钥宽限期） ──
# 格式：逗号分隔，第一个为最新密钥，后续为旧密钥（48h宽限期）
AUTH_SECRETS = [
    s.strip() for s in os.getenv("BAA_AUTH_SECRET", "").split(",") if s.strip()
]  # function call
if not AUTH_SECRETS:  # check: negated condition
    # 开发模式默认密钥（生产环境必须通过环境变量设置）
    AUTH_SECRETS = ["baa-dev-secret-change-in-production"]  # assignment


# ── 线程池（CPU密集型引擎任务用） ─────────────────────────
import asyncio  # stdlib: async
from concurrent.futures import ThreadPoolExecutor  # import

# 引擎线程池：用于在独立线程中执行 CPU 密集的图纸分析任务
# 避免阻塞 FastAPI 的异步事件循环
ENGINE_THREAD_POOL = ThreadPoolExecutor(  # assignment
    max_workers=min(8, (os.cpu_count() or 4) * 2),  # get minimum
    thread_name_prefix="baa-engine",  # assignment
)  # code


# ── 授权验证 ──────────────────────────────────────────────

# HMAC-SHA256 签名与 Base64 编解码（用于 auth_token 的 JWT 式实现）
import hmac  # import
import hashlib  # stdlib: hashing
import base64  # stdlib: base64

# ── API密钥管理 ──────────────────────────────────────────

# 密钥管理器：支持 API Key 的创建、轮换、撤销、权限验证
from src.baa_engine.api_key_manager import get_key_manager, ApiKeyPermission  # import

# 反馈引擎：用户违规申诉 → 模型微调的学习闭环
from src.baa_engine.feedback_engine import FeedbackManager, LearningEngine  # import


def generate_auth_token(
    payload: dict, secret: str = None
) -> str:  # function: def generate_auth_token(payload: dict, secret: str = None) -
    """生成 auth_token（JWT格式，HMAC-SHA256）
    默认使用最新密钥
    """
    if secret is None:  # check: value is None
        secret = AUTH_SECRETS[0]  # 使用最新密钥
    # ── 构造 JWT Header（算法 + 类型） ──────────────────────
    header = {"alg": "HS256", "typ": "JWT"}  # assignment
    header_b64 = (
        base64.urlsafe_b64encode(json.dumps(header, separators=(",", ":")).encode())  # assignment
        .rstrip(b"=")
        .decode()
    )  # serialize JSON
    # ── Base64 编码 Payload ─────────────────────────────────
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())  # assignment
        .rstrip(b"=")
        .decode()
    )  # serialize JSON
    # ── HMAC-SHA256 签名 ────────────────────────────────────
    signing_input = f"{header_b64}.{payload_b64}"  # assignment
    sig = hmac.new(  # assignment
        secret.encode(), signing_input.encode(), hashlib.sha256  # function call
    ).digest()  # function call
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()  # function call
    return f"{header_b64}.{payload_b64}.{sig_b64}"  # return


def verify_auth_token(
    token: str,
) -> Optional[dict]:  # function: def verify_auth_token(token: str) -> Optional[dict]:
    """验证 auth_token，使用所有活跃密钥（支持密钥宽限期）

    遍历 AUTH_SECRETS 列表，依次尝试用每个密钥验证签名。
    旧密钥在 48h 宽限期内仍有效，确保密钥轮换期间不影响已有 token。
    """
    for secret in AUTH_SECRETS:  # 循环
        result = _verify_with_secret(token, secret)  # function call
        if result is not None:  # check: value is not None
            return result  # return
    return None  # return: None


def _verify_with_secret(
    token: str, secret: str
) -> Optional[dict]:  # function: def _verify_with_secret(token: str, secret: str) -> Optional
    """用单个密钥验证 token

    Args:
        token: 待验证的 JWT 格式 token
        secret: HMAC 签名密钥

    Returns:
        验证通过返回 payload 字典，失败返回 None
    """
    try:  # 尝试
        # ── 解析 JWT 三段式结构 ──────────────────────────────
        parts = token.split(".")  # function call
        if len(parts) != 3:  # check: length
            return None  # return: None

        header_b64, payload_b64, sig_b64 = parts  # assignment
        signing_input = f"{header_b64}.{payload_b64}"  # assignment

        def add_padding(s):  # function: def add_padding(s):
            """Base64 URL-safe 解码需要补齐 '=' 填充符"""
            return s + "=" * (4 - len(s) % 4)  # return

        # ── 重新计算签名并与 token 中的签名比较 ──────────────
        expected_sig = hmac.new(  # assignment
            secret.encode(), signing_input.encode(), hashlib.sha256  # function call
        ).digest()  # function call

        actual_sig = base64.urlsafe_b64decode(add_padding(sig_b64))  # function call
        if not hmac.compare_digest(expected_sig, actual_sig):  # check: negated condition
            return None  # return: None

        # ── 解码 payload ─────────────────────────────────────
        payload = json.loads(base64.urlsafe_b64decode(add_padding(payload_b64)))  # deserialize JSON

        # ── 验证有效期（兼容带时区和不带时区的时间字符串） ──
        expires = payload.get("expires_at")  # function call
        if expires:  # condition: expires:
            from datetime import timezone  # stdlib: timing

            exp_time = datetime.fromisoformat(expires)  # function call
            if exp_time.tzinfo is None:  # check: value is None
                exp_time = exp_time.replace(tzinfo=timezone.utc)  # function call
            if datetime.now(timezone.utc) > exp_time:  # check: numeric comparison
                return None  # token 已过期

        return payload  # return
    # 异常处理
    except Exception:  # 捕获异常
        return None  # return: None


# ── FastAPI 应用 ──────────────────────────────────────────

# 前端静态文件路径
FRONTEND_DIR = PROJECT_ROOT / "src" / "frontend"  # assignment


# ── 引擎预热（app启动时加载） ──────────────────────────────


def _load_engine():  # function: def _load_engine():
    """预热加载引擎模块，每个 worker 启动时执行一次"""
    from src.baa_engine.drawing_parser import DrawingParser  # import
    from src.baa_engine.semantic_analyzer import SemanticAnalyzer  # import
    from src.baa_engine.atomic_functions import FuncRegistry  # import
    from src.baa_engine.attribution_analyzer import AttributionAnalyzer  # import
    from src.baa_engine.spec_repository import SpecRepository  # import

    global _drawing_parser, _semantic_analyzer, _func_registry, _attribution_analyzer, _spec_repo, _feedback_manager, _learning_engine  # 全局变量
    _drawing_parser = DrawingParser()  # function call
    _semantic_analyzer = SemanticAnalyzer()  # function call
    _func_registry = FuncRegistry()  # function call
    _attribution_analyzer = AttributionAnalyzer()  # function call
    _spec_repo = SpecRepository()  # function call
    _feedback_manager = FeedbackManager(DATA_DIR)  # function call
    _learning_engine = LearningEngine(_feedback_manager)  # function call
    print(
        f"[BAA] 引擎已预热: {_func_registry.count}个原子函数, {_spec_repo.count}条规范"
    )  # print output
    print(f"[BAA] 反馈闭环已加载: {_feedback_manager.stats()['total']}条申诉")  # print output


from contextlib import asynccontextmanager  # import


import gc  # stdlib: garbage collection

# ── 内存监控（每 300 秒触发 GC，防止内存泄漏） ─────────
_GC_INTERVAL = 300  # 秒
_last_gc_time = 0  # 上次 GC 时间戳


def _periodic_gc():  # function: def _periodic_gc():
    """定时 GC 回收，防止大图纸解析后的内存堆积"""
    global _last_gc_time  # code
    now = time.time()  # get current time
    if now - _last_gc_time > _GC_INTERVAL:  # check: numeric comparison
        gc.collect()  # function call
        _last_gc_time = now  # assignment


# ── 并发限制（防止大图纸爆炸） ──────────────────────────
MAX_CONCURRENT_REVIEWS = 4  # 最大并发审查数
_review_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REVIEWS)  # function call


@asynccontextmanager  # code
async def lifespan(app: FastAPI):  # function call
    """应用生命周期管理

    启动时：在线程池中异步预热引擎各模块，避免阻塞事件循环
    关闭时：优雅关闭线程池
    """
    # 启动时：预热引擎
    loop = asyncio.get_event_loop()  # function call
    await loop.run_in_executor(ENGINE_THREAD_POOL, _load_engine)  # 操作
    yield  # 生成
    # 关闭时：清理线程池
    ENGINE_THREAD_POOL.shutdown(wait=False)  # function call


app = FastAPI(title="BAA API", version="1.0.0", lifespan=lifespan)  # function call
security = HTTPBearer(auto_error=False)  # function call

# ── 挂载前端静态文件 ──────────────────────────────────────
if FRONTEND_DIR.exists():  # condition: FRONTEND_DIR.exists():
    app.mount(
        "/static", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend"
    )  # function call


@app.get("/")  # function call
async def root():  # function call
    """返回前端 UI 页面

    优先返回静态 HTML 页面（前端 SPA）；
    如果前端文件不存在，降级返回 JSON 格式的 API 信息。
    """
    from fastapi.responses import HTMLResponse  # fastapi: response types

    index_path = FRONTEND_DIR / "index.html"  # assignment
    if index_path.exists():  # condition: index_path.exists():
        content = index_path.read_text(encoding="utf-8")  # function call
        return HTMLResponse(content=content, status_code=200)  # return
    # 降级：返回 JSON 信息（前端文件未部署时使用）
    return {  # return: dict
        "service": "BAA - Building Audit Assistant",  # 字段
        "version": "1.0.0",  # 字段
        "api_docs": "/docs",  # 字段
        "endpoints": {  # 字段
            "/health": "服务健康检查",  # 字段
            "/deconstruct": "图纸解析与违规范判定",  # 字段
            "/review": "图纸合规审查（详细报告）",  # 字段
            "/reconstruct": "图纸重构",  # 字段
            "/order/{order_id}": "查询订单/任务状态",  # 字段
        },  # code
        "note": "前端 UI 文件未找到，请检查 src/frontend/index.html",  # 字段
    }  # code


# ── CORS 中间件（允许跨域访问） ────────────────────────────
app.add_middleware(  # code
    CORSMiddleware,  # 解包
    allow_origins=["*"],  # 允许所有来源（开发阶段）
    allow_credentials=True,  # assignment
    allow_methods=["*"],  # assignment
    allow_headers=["*"],  # assignment
)  # code


def get_api_key(
    authorization: str = Query("", description="Bearer API Key")
):  # function: def get_api_key(authorization: str = Query("", description="
    """从 Query 参数中获取 API Key（兼容 Swagger UI 调试）"""


def verify_api_key(request: Request):  # function: def verify_api_key(request: Request):
    """验证 API Key（使用 ApiKeyManager）

    验证流程：
    1. 如果未配置 API_KEYS（开发模式），跳过验证，返回 anonymous
    2. 从 Authorization Header 提取 Bearer token
    3. 使用 ApiKeyManager 验证密钥是否有效
    4. 如果是环境变量中的密钥也放行
    5. 开发模式下无效密钥也放行（anonymous）
    """
    if not API_KEYS:  # check: negated condition
        return "anonymous"  # return
    auth_header = request.headers.get("authorization", "")  # function call

    # 根据条件判断分支：if auth_header.startswith("Bearer ")
    if auth_header.startswith("Bearer "):  # condition: auth_header.startswith("Bearer "):
        token = auth_header[7:]  # assignment
    else:  # 否则
        return "anonymous"  # 开发模式：没传key也放行

    # 使用 ApiKeyManager 验证（数据库中的密钥）
    km = get_key_manager()  # function call
    key_info = km.validate_key(token)  # function call
    if key_info:  # condition: key_info:
        km.record_usage(token)  # function call
        return token  # return

    # 环境变量密钥也放行
    if token in API_KEYS:  # check: membership test
        return token  # return

    # 开发模式：没传有效key也放行
    return "anonymous"  # return


def require_admin(
    request: Request, api_key: str = ""
):  # function: def require_admin(request: Request, api_key: str = ""):
    """验证 admin 权限（用于 admin 端点）

    验证逻辑：
    1. 开发模式（API_KEYS 为空）时不校验，直接放行
    2. 使用 ApiKeyManager 验证密钥是否具有 admin 权限
    3. 环境变量中的密钥也视为 admin 权限
    """
    if not API_KEYS:  # check: negated condition
        return "anonymous"  # return
    km = get_key_manager()  # function call
    key_info = km.validate_key(api_key)  # function call
    if key_info and key_info.get("permission") == "admin":  # check: AND condition
        return api_key  # return
    # 环境变量key也视为admin
    if api_key and api_key in API_KEYS:  # check: membership test
        return api_key  # return
    raise HTTPException(
        status_code=403,
        detail={  # 抛出异常
            "status": "error",
            "error_code": "FORBIDDEN",  # 字段
            "message": "需要admin权限",  # 字段
        },
    )  # code


# ── 文件管理 ──────────────────────────────────────────────


def generate_file_id() -> str:  # function: def generate_file_id() -> str:
    """生成唯一文件标识符（UUID 前 12 位）"""
    return f"baa-file-{uuid.uuid4().hex[:12]}"  # return


def store_file(
    content: bytes, file_id: str, extension: str
) -> Path:  # function: def store_file(content: bytes, file_id: str, extension: str)
    """将上传文件保存到磁盘

    Args:
        content: 文件二进制内容
        file_id: 文件唯一标识符
        extension: 文件扩展名（dwg/dxf）

    Returns:
        保存后的文件路径
    """
    path = FILES_DIR / f"{file_id}.{extension}"  # assignment
    path.write_bytes(content)  # function call
    return path  # return


def get_file_path(
    file_id: str,
) -> Optional[Path]:  # function: def get_file_path(file_id: str) -> Optional[Path]:
    """根据文件 ID 查找已存储的图纸文件

    遍历所有支持的文件格式，找到匹配的文件。

    Args:
        file_id: 文件唯一标识符

    Returns:
        文件路径（如果存在），否则 None
    """
    for ext in SUPPORTED_FORMATS:  # 循环
        path = FILES_DIR / f"{file_id}.{ext}"  # assignment
        if path.exists():  # condition: path.exists():
            return path  # return
    return None  # return: None


# ── 引擎导入（懒加载） ──────────────────────────────────

# ── 引擎引用（由 lifespan 预热加载） ──────────────────────

# 各引擎模块的全局引用，在 app 启动时通过 _load_engine() 初始化
_drawing_parser = None  # 图纸解析器
_semantic_analyzer = None  # 语义分析器
_func_registry = None  # 原子函数注册表
_attribution_analyzer = None  # 属性推断引擎
_spec_repo = None  # 规范知识库

# ── 反馈闭环引擎（P10） ────────────────────────────────────
_feedback_manager: Optional[FeedbackManager] = None  # assignment
_learning_engine: Optional[LearningEngine] = None  # 操作


@app.get("/health")  # function call
async def health():  # function call
    """增强型健康检查接口

    返回服务状态及各子系统（引擎、规范库、解析器、YOLO）的运行状态。
    用于 Docker 健康检查、负载均衡心跳检测。

    Returns:
        dict: {
            status: "ok" | "degraded",
            version: 当前版本号,
            uptime_seconds: 服务运行秒数,
            subsystems: 各子系统的状态详情
        }
    """
    engine_ok = _func_registry is not None  # assignment
    spec_ok = _spec_repo is not None  # assignment
    parser_ok = _drawing_parser is not None  # assignment
    yolo_ok = False  # assignment
    yolo_info = "未加载"  # assignment
    try:  # 尝试
        from src.baa_engine.yolo_integrator import YOLODetectionIntegrator  # import

        yolo = YOLODetectionIntegrator()  # function call
        if yolo.load_model():  # condition: yolo.load_model():
            yolo_ok = True  # assignment
            yolo_info = "就绪"  # assignment
    except Exception:  # 捕获异常
        yolo_info = "不可用"  # assignment

    import psutil  # psutil: system memory

    process = psutil.Process()  # function call
    mem_info = process.memory_info()  # function call

    all_ok = engine_ok and spec_ok and parser_ok  # assignment
    return {  # return: dict
        "status": "ok" if all_ok else "degraded",  # 字段
        "version": "1.25.0",  # 字段
        "uptime_seconds": int(time.time() - _start_time),  # 字段
        "engine_status": "ready" if all_ok else "degraded",  # 字段
        "supported_formats": list(SUPPORTED_FORMATS),  # 字段
        "api_version": "v1",  # 字段
        "subsystems": {  # 字段
            "engine": {"status": "ok" if engine_ok else "down"},  # 字段
            "spec_repository": {"status": "ok" if spec_ok else "down"},  # 字段
            "drawing_parser": {"status": "ok" if parser_ok else "down"},  # 字段
            "yolo_integrator": {
                "status": "ok" if yolo_ok else "unavailable",
                "info": yolo_info,
            },  # 字段
        },  # code
        "data_dir": str(DATA_DIR),  # 字段
        "memory": {  # 字段
            "rss_mb": round(mem_info.rss / 1024 / 1024, 1),  # 字段
            "vms_mb": round(mem_info.vms / 1024 / 1024, 1),  # 字段
        },  # code
    }  # code


# ── 记录服务启动时间 ───────────────────────────────────────
_start_time = time.time()  # get current time


@app.post("/deconstruct")  # function call
async def deconstruct(  # code
    file: UploadFile = File(...),  # function call
    building_type: str = Query(
        "civil", description="建筑类型: civil(民用) / industrial(工业)"
    ),  # function call
    standard: str = Query(
        "GB 50016-2014", description="规范标准: GB 50016-2014 / NFPA 101-2021 / NFPA 5000-2021"
    ),  # function call
    use_yolo: bool = Query(True, description="是否使用 YOLO 图元检测增强"),  # function call
    yolo_device: str = Query(
        "cpu", description="YOLO 推理设备: cpu(默认) / xpu(Intel Arc GPU)"
    ),  # function call
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """图纸解构（免费端点）

    将上传的 DWG/DXF 图纸解析为结构化实体数据，包括：
    1. DWG/DXF → 图元解析（DrawingParser）
    2. 语义分析（SemanticAnalyzer）— 识别墙、门、窗、楼梯等
    3. 可选 YOLO 检测增强 — 使用 CV 模型辅助识别
    4. 尺寸标注注入（DimensionParser）— 自动反推实体属性
    5. 规范判定 — 按 GB50016 检查每类实体的合规性
    6. 结果聚合 — 统计、去重、分类输出

    Returns:
        dict: {status, elements, findings, summary, ...}
    """
    # ── 检查文件格式 ────────────────────────────────────────
    filename = file.filename or "unknown"  # assignment
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""  # function call

    if ext not in SUPPORTED_FORMATS:  # check: membership test
        raise HTTPException(  # 抛出异常
            status_code=400,  # assignment
            detail={  # assignment
                "status": "error",  # 字段
                "error_code": "UNSUPPORTED_FORMAT",  # 字段
                "message": f"不支持的文件格式: {ext}。支持: {', '.join(SUPPORTED_FORMATS)}",  # 字段
            },  # code
        )  # code

    # ── 检查文件大小 ────────────────────────────────────────
    content = await file.read()  # function call
    if len(content) > MAX_FILE_SIZE:  # check: numeric comparison
        raise HTTPException(  # 抛出异常
            status_code=400,  # assignment
            detail={  # assignment
                "status": "error",  # 字段
                "error_code": "FILE_TOO_LARGE",  # 字段
                "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",  # 字段
            },  # code
        )  # code

    # ── 存储文件到磁盘 ──────────────────────────────────────
    file_id = generate_file_id()  # function call
    file_path = store_file(content, file_id, ext)  # function call

    # ── 调用核心引擎进行解析 ─────────────────────────────────
    start = time.time()  # get current time
    loop = asyncio.get_event_loop()  # function call

    # Step 1: 图纸解析（CPU密集型 → 线程池）
    # 将 DWG/DXF 文件解析为基本图元（线、弧、圆、文字等）
    result = await loop.run_in_executor(  # assignment
        ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id  # 操作
    )  # code

    # ── P18 截断警告（部分解析成功） ─────────────────────
    page_warning = None  # assignment
    if result.error and "截断" in result.error:  # check: membership test
        page_warning = result.error  # assignment
        result.success = True  # assignment
        result.error = None  # assignment

    if not result.success:  # check: negated condition
        return {  # return: dict
            "status": "error",  # 字段
            "error_code": "PARSE_FAILED",  # 字段
            "message": f"图纸解析失败: {result.error}",  # 字段
            "file_id": file_id,  # 字段
        }  # code

    # Step 2: 语义分析（CPU密集型 → 线程池）
    # 识别墙、门、窗、楼梯、防火分区等语义实体
    semantic = await loop.run_in_executor(  # assignment
        ENGINE_THREAD_POOL,  # 解包
        lambda: _semantic_analyzer.analyze(  # 操作
            result.primitives, result.dimensions, building_type=building_type  # 解包  # assignment
        ),  # code
    )  # code
    entities = semantic["entities"]  # assignment
    relations = semantic["relations"]  # assignment

    # Step 2.5: YOLO 图元检测增强（可选）
    # 使用 CV 模型辅助识别规则解析遗漏的实体
    if use_yolo:  # condition: use_yolo:
        try:  # 尝试
            from src.baa_engine.yolo_integrator import YOLODetectionIntegrator  # import

            yolo = YOLODetectionIntegrator(device=yolo_device)  # function call
            if yolo.load_model():  # condition: yolo.load_model():
                _, dets = yolo.render_and_predict(str(file_path))  # function call
                yolo_entities = yolo.detections_to_entities(dets)  # function call
                # 合并到实体列表（去重，优先保留规则解析结果）
                existing_types = set(e.get("type", "") for e in entities)  # function call
                for ye in yolo_entities:  # 循环
                    if ye["type"] not in existing_types:  # check: membership test
                        entities.append(ye)  # append to list
        except Exception as yolo_e:  # 捕获异常
            # YOLO 失败不影响主流程
            pass  # 占位

    # Step 2.75: DIMENSION 尺寸标注注入（自动反推实体属性）
    try:  # 尝试
        from src.baa_engine.dimension_parser import DimensionParser  # import

        dp = DimensionParser()  # function call
        dims = dp.extract_dimensions(str(file_path))  # function call
        if dims:  # condition: dims:
            entities = dp.inject_into_entities(dims, entities)  # function call
    except Exception:  # 捕获异常
        pass  # 占位

    # Step 3: 规范判定（使用 building_type 确定阈值，含去重）
    # 遍历所有实体和所有原子函数，逐项检查合规性
    from src.baa_engine.spec_repository import SpecRepository  # import

    repo = SpecRepository()  # function call
    findings = []  # assignment
    registry_funcs = _func_registry.list_all()  # check all true
    total_checks = 0  # assignment
    seen_violations = set()  # (clause_id, entity_type) 用于 FAIL 去重

    # 遍历处理
    for e in entities:  # 循环
        for func in registry_funcs:  # 循环
            total_checks += 1  # accumulate
            # 根据建筑类型和规范标准获取阈值参数
            threshold_val, unit, op = repo.get_threshold(
                func.clause_id, building_type, standard
            )  # function call
            func.threshold = threshold_val  # assignment
            func.unit = unit  # assignment
            func.operator = op  # assignment
            r = _func_registry.execute_with_timeout(func, e)  # function call
            if r is not None and r.result != "PASS":  # check: value is not None
                # 去重：同一 clause_id + 同一 entity_type 只记一次 FAIL
                etype = e.get("type", "")  # function call
                dedup_key = (func.clause_id, etype)  # function call
                is_dup = dedup_key in seen_violations  # assignment
                if r.result == "FAIL":  # condition: r.result == "FAIL":
                    seen_violations.add(dedup_key)  # function call

                clause = {  # assignment
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # code
                f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])  # function call
                # 详细的违规信息输出
                finding_detail = {  # assignment
                    "finding_id": f.finding_id,  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "clause_title": func.name,  # 字段
                    "description": func.description,  # 字段
                    "entity_type": etype,  # 字段
                    "result": r.result,  # 字段
                    "severity": getattr(r, "severity", "major"),  # 字段
                    "extracted_value": getattr(
                        r, "extracted_value", getattr(r, "value", 0)
                    ),  # 字段
                    "required_value": threshold_val,  # 字段
                    "explanation": getattr(
                        f, "explanation", f.description[:100] if hasattr(f, "description") else ""
                    ),  # 字段
                    "is_duplicate": is_dup,  # 字段
                }  # code
                findings.append(finding_detail)  # append to list

    # 缺失检查：对 EXIST-* 函数检查是否有匹配实体
    # 例如"应有防火门"→检查是否存在 fire_door 实体
    for func in registry_funcs:  # 循环
        if func.category.value != "exist":  # check: OR condition
            continue  # 继续循环
        has_match = any(func.matches(e) for e in entities)  # check any true
        if not has_match:  # check: negated condition
            total_checks += 1  # accumulate
            r = _func_registry.execute_with_timeout(func, None)  # function call
            if r is not None and r.result != "PASS":  # check: value is not None
                dedup_key = (func.clause_id, "missing")  # function call
                is_dup = dedup_key in seen_violations  # assignment
                if r.result == "FAIL":  # condition: r.result == "FAIL":
                    seen_violations.add(dedup_key)  # function call

                clause = {  # assignment
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # code
                f = _attribution_analyzer.build_finding(
                    r, clause, {}, entities[:5]
                )  # function call
                finding_detail = {  # assignment
                    "finding_id": f.finding_id,  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "clause_title": func.name,  # 字段
                    "description": func.description,  # 字段
                    "entity_type": "missing",  # 字段
                    "result": r.result,  # 字段
                    "severity": "critical",  # 字段
                    "extracted_value": 0,  # 字段
                    "required_value": 1,  # 字段
                    "explanation": f"缺少{func.name}相关实体（{func.description}）",  # 字段
                    "is_duplicate": is_dup,  # 字段
                }  # code
                findings.append(finding_detail)  # append to list

    # 统计
    type_stats = {}  # assignment
    for e in entities:  # 循环
        t = e["type"]  # assignment
        if t not in type_stats:  # check: membership test
            type_stats[t] = {"count": 0, "bbox_areas": []}  # 操作
        type_stats[t]["count"] += 1  # 操作
        bbox = e["bbox"]  # assignment
        type_stats[t]["bbox_areas"].append(bbox.get("width", 0) * bbox.get("height", 0))  # 操作

    elements = []  # assignment
    for t, stats in sorted(type_stats.items()):  # 循环
        areas = stats["bbox_areas"]  # assignment
        total_area = sum(areas) if areas else 0  # aggregate sum
        elem = {"type": t, "count": stats["count"]}  # assignment
        if t in ("wall", "corridor", "stair"):  # check: membership test
            elem["total_length_m"] = round(total_area**0.5, 1)  # 操作
        elif t in ("door", "fire_door", "window"):  # 分支
            elem["total_count"] = stats["count"]  # 操作
        elif t == "fire_zone":  # 分支
            elem["total_area_sqm"] = round(total_area, 1)  # 操作
        elif t in ("equipment", "foundation", "column"):  # 分支
            elem["total_count"] = stats["count"]  # 操作
        elif t == "other":  # 分支
            elem["total_count"] = stats["count"]  # 操作
        elements.append(elem)  # append to list

    elapsed = int((time.time() - start) * 1000)  # get current time

    # ── 统计违规严重度分布（去重后） ────────────────────────
    fail_count = len(
        [f for f in findings if f["result"] == "FAIL" and not f["is_duplicate"]]
    )  # get length
    warn_count = len(
        [f for f in findings if f["result"] == "WARN" and not f["is_duplicate"]]
    )  # get length
    critical_count = len(
        [f for f in findings if f.get("severity") == "critical" and not f["is_duplicate"]]
    )  # get length

    result = {  # assignment
        "status": "success",  # 字段
        "elements": elements,  # 实体类型统计
        "relations": len(relations),  # 实体间关系数量
        "findings": findings,  # 完整违规详情（含去重标记）
        "total_checks": total_checks,  # 总检查项数
        "summary": {  # 字段
            "total_violations": fail_count,  # 字段
            "warnings": warn_count,  # 字段
            "critical": critical_count,  # 字段
            "total_checks": total_checks,  # 字段
        },  # code
        "confidence": 0.85 if len(entities) > 0 else 0,  # 解析置信度
        "file_id": file_id,  # 字段
        "building_type": building_type,  # 字段
        "standard": standard,  # code
        "processing_time_ms": elapsed,  # 字段
    }  # code

    # ── P18 大图纸警告 ────────────────────────────────
    if page_warning:  # condition: page_warning:
        result["page_warning"] = page_warning  # assignment

    # ── xref 外部参照警告 ────────────────────────────────
    if result.warning:  # condition: result.warning:
        result["xref_warning"] = result.warning  # assignment

    # 根据条件判断分支：if use_yolo
    if use_yolo:  # condition: use_yolo:
        result["yolo_entities"] = len(yolo_entities)  # 操作
        result["yolo_enabled"] = True  # 操作

    return result  # return


@app.post("/review")  # function call
async def review(  # code
    file: UploadFile = File(...),  # function call
    full: bool = Query(False, description="返回完整图元列表"),  # function call
    building_type: str = Query(
        "civil", description="建筑类型: civil(民用) / industrial(工业)"
    ),  # function call
    building_types: Optional[List[str]] = Query(
        None, description="多建筑类型列表（混合建筑场景）"
    ),  # function call
    standard: str = Query(
        "GB 50016-2014", description="规范标准: GB 50016-2014 / NFPA 101-2021 / NFPA 5000-2021"
    ),  # function call
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """图纸合规审查（免费试用）

    对上传的 DWG/DXF 图纸进行完整合规审查，返回：
    - 审查摘要（实体统计、检查项数、违规分布）
    - 违规详情（每条违规的 clause_id、提取值、要求值、差值）
    - 修正建议（基于 correction_engine 生成）

    支持多标准：
    - GB 50016-2014（中国建筑防火规范，默认）
    - NFPA 101-2021（美国生命安全规范）
    - NFPA 5000-2021（美国建筑规范）

    与 /deconstruct 的区别：
    - /deconstruct 侧重"拆解"，输出结构化实体数据
    - /review 侧重"审查"，输出合规报告和修正建议
    """
    # ── 检查文件格式 ────────────────────────────────────────
    filename = file.filename or "unknown"  # assignment
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""  # function call

    if ext not in SUPPORTED_FORMATS:  # check: membership test
        raise HTTPException(  # 抛出异常
            status_code=400,  # assignment
            detail={  # assignment
                "status": "error",  # 字段
                "error_code": "UNSUPPORTED_FORMAT",  # 字段
                "message": f"不支持的文件格式: {ext}",  # 字段
            },  # code
        )  # code

    # ── 检查文件大小 ────────────────────────────────────────
    content = await file.read()  # function call
    if len(content) > MAX_FILE_SIZE:  # check: numeric comparison
        raise HTTPException(  # 抛出异常
            status_code=400,  # assignment
            detail={  # assignment
                "status": "error",  # 字段
                "error_code": "FILE_TOO_LARGE",  # 字段
                "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",  # 字段
            },  # code
        )  # code

    # ── 存储文件到磁盘 ──────────────────────────────────────
    file_id = generate_file_id()  # function call
    file_path = store_file(content, file_id, ext)  # function call

    # ── 缓存检查：相同文件内容+参数秒级返回 ──────────────────
    file_hash = hashlib.sha256(content).hexdigest()[:32]  # function call
    cache_key = make_cache_key(file_hash, standard, building_type)  # function call
    # 先查内存缓存（最快）
    cached = _review_cache.get(cache_key)  # function call
    if cached is not None:  # check: value is not None
        cached["file_id"] = file_id  # assignment
        return cached  # return
    # 再查持久化缓存（服务重启后恢复）
    persistent = _persistent_cache.get(cache_key, "review_result")  # function call
    if persistent is not None:  # check: value is not None
        _review_cache[cache_key] = persistent  # assignment
        persistent["file_id"] = file_id  # assignment
        return persistent  # return

    start = time.time()  # get current time
    loop = asyncio.get_event_loop()  # function call

    # 并发控制：等待排队（最多 {MAX_CONCURRENT_REVIEWS} 个并发槽位）
    async with _review_semaphore:  # code
        # Step 1: 图纸解析（CPU密集型 → 线程池）
        result = await loop.run_in_executor(  # assignment
            ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id  # 操作
        )  # code
        if not result.success:  # check: negated condition
            return {  # return: dict
                "status": "error",  # 字段
                "error_code": "PARSE_FAILED",  # 字段
                "message": f"图纸解析失败: {result.error}",  # 字段
                "file_id": file_id,  # 字段
            }  # code

        # Step 2: 语义分析（CPU密集型 → 线程池）
        semantic = await loop.run_in_executor(  # assignment
            ENGINE_THREAD_POOL,  # 解包
            lambda: _semantic_analyzer.analyze(  # 操作
                result.primitives,
                result.dimensions,  # 解包
                building_type=building_type,  # assignment
            ),  # code
        )  # code
        entities = semantic["entities"]  # assignment

    # 多建筑类型：向后兼容，building_types 为空时使用 building_type
    effective_types = building_types if building_types else [building_type]  # assignment

    # Step 3: 规范判定（使用 building_type 确定阈值）
    from src.baa_engine.spec_repository import SpecRepository  # import

    repo = SpecRepository()  # function call
    from collections import Counter  # stdlib: collections

    clause_results = Counter()  # function call
    details = []  # assignment
    registry_funcs = _func_registry.list_all()  # check all true

    # 收集已出现的实体类型
    found_entity_types = set(e["type"] for e in entities)  # function call

    # 多建筑类型并行匹配：取最严格阈值
    def get_strict_threshold(
        clause_id: str,
    ) -> tuple:  # function: def get_strict_threshold(clause_id: str) -> tuple:
        worst_val, worst_unit, worst_op = None, None, None  # assignment
        for bt in effective_types:  # loop: iterate
            v, u, o = repo.get_threshold(clause_id, bt)  # function call
            if worst_val is None or v > worst_val:  # check: value is None
                worst_val, worst_unit, worst_op = v, u, o  # assignment
        return worst_val, worst_unit, worst_op  # return

    # P32: 链式依赖执行 — 按依赖拓扑顺序，结果在函数间共享
    # 对每个实体，按依赖拓扑顺序执行所有原子函数
    func_ids = [f.func_id for f in registry_funcs]  # 提取所有函数ID
    for e in entities:  # 循环
        # 使用链式执行：依赖函数先执行，结果缓存后传递给后续函数
        chained_results = _func_registry.execute_chained(func_ids, e)  # function call
        for fid, r in chained_results.items():  # 循环
            func = _func_registry.get(fid)  # function call
            if func is None:  # condition: func is None:
                continue  # 跳过
            threshold_val, unit, op = get_strict_threshold(func.clause_id)  # function call
            # 使用链式执行结果，无需重复设置阈值（已在chained_results中）
            if r is None:  # check: value is None
                continue  # 继续循环
            clause_results[func.clause_id] += 1  # accumulate
            if r.result != "PASS":  # condition: r.result != "PASS":
                clause = {  # assignment
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # code
                f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])  # function call
                details.append(
                    {  # code
                        "entity_id": e.get("id", e.get("type", "")),  # 字段
                        "entity_type": e["type"],  # 字段
                        "clause_id": f.clause.get("clause_id", ""),  # 字段
                        "clause_title": f.clause.get("title", ""),  # 字段
                        "result": f.judgement["result"],  # 字段
                        "extracted_value": f.extracted_params["extracted_value"],  # 字段
                        "required_value": f.extracted_params.get("required_value", 1.2),  # 字段
                        "difference": f.extracted_params.get("difference", 0),  # 字段
                        "explanation": f.explanation[:120],  # 字段
                    }
                )  # code

    # 缺失检查：对 EXIST-* 函数检查是否有匹配实体
    for func in registry_funcs:  # 循环
        if func.category.value != "exist":  # check: OR condition
            continue  # 继续循环
        has_match = any(func.matches(e) for e in entities)  # check any true
        if not has_match:  # check: negated condition
            r = _func_registry.execute_with_timeout(func, None)  # 触发缺失检查模式
            if r is not None and r.result != "PASS":  # check: value is not None
                clause = {  # assignment
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # code
                f = _attribution_analyzer.build_finding(
                    r, clause, {}, entities[:5]
                )  # function call
                details.append(
                    {  # code
                        "entity_id": "",  # 字段
                        "entity_type": "missing",  # 字段
                        "clause_id": f.clause.get("clause_id", ""),  # 字段
                        "clause_title": f.clause.get("title", ""),  # 字段
                        "result": f.judgement["result"],  # 字段
                        "extracted_value": 0.0,  # 字段
                        "required_value": f.extracted_params.get("required_value", 1.0),  # 字段
                        "difference": -f.extracted_params.get("required_value", 1.0),  # 字段
                        "explanation": f.explanation[:120],  # 字段
                    }
                )  # code

    elapsed = int((time.time() - start) * 1000)  # get current time

    # ── 统计 ─────────────────────────────────────────────────
    entity_types = Counter(e["type"] for e in entities)  # 各类型实体数量
    violation_count = Counter(d["clause_id"] for d in details)  # 各规范条款违规数

    # ── 计算综合评分（P36） ────────────────────────────────
    total_score = 100.0  # assignment
    if len(entities) > 0 and len(details) > 0:  # check: numeric comparison
        violation_deduction = len(details) * 5.0  # get length
        critical_count = sum(1 for d in details if d.get("severity") == "critical")  # aggregate sum
        major_count = sum(1 for d in details if d.get("severity") == "major")  # aggregate sum
        total_score = max(
            0, 100.0 - violation_deduction - critical_count * 10 - major_count * 3
        )  # get maximum

    avg_confidence = 1.0  # assignment
    confidences = [d.get("confidence", 1.0) for d in details if "confidence" in d]  # function call
    if confidences:  # condition: confidences:
        avg_confidence = sum(confidences) / len(confidences)  # get length

    response_data = {  # assignment
        "status": "success",  # 字段
        "summary": {  # 字段
            "total_entities": len(entities),  # 字段
            "entity_types": dict(entity_types),  # 字段
            "total_checks": len(entities) * len(registry_funcs),  # 字段
            "violations": len(details),  # 字段
            "violation_by_clause": dict(violation_count.most_common(10)),  # 字段
            "score": total_score,  # 字段
            "avg_confidence": round(avg_confidence, 2),  # 字段
        },  # code
        "details": details[:100],  # 最多返回100条详情
        "file_id": file_id,  # 字段
        "building_type": building_type,  # 字段
        "standard": standard,  # code
        "processing_time_ms": elapsed,  # 字段
    }  # code

    # ── 生成修正建议（基于 CorrectionEngine） ────────────────
    try:  # 尝试
        from src.baa_engine.correction_engine import CorrectionEngine  # import

        correction_engine = CorrectionEngine()  # function call
        review_result_for_correction = {  # assignment
            "findings": [
                {  # 字段
                    "entity_id": d["entity_id"],  # 字段
                    "entity_type": d["entity_type"],  # 字段
                    "clause_id": d["clause_id"],  # 字段
                    "clause_title": d["clause_title"],  # 字段
                    "extracted_value": d["extracted_value"],  # 字段
                    "required_value": d["required_value"],  # 字段
                    "difference": d["difference"],  # 字段
                }
                for d in details
            ]  # code
        }  # code
        corrections = correction_engine.generate_for_result(
            review_result_for_correction
        )  # function call
        response_data["corrections"] = corrections  # 操作
    except Exception as e:  # 捕获异常
        response_data["corrections"] = []  # 操作

    # ── 如果请求 full 模式，返回完整图元列表 ─────────────────
    if full:  # condition: full:
        response_data["all_entities"] = [  # 操作
            {"id": e.get("id", e.get("type", "")), "type": e["type"], "bbox": e["bbox"]}  # 字面量
            for e in entities  # 循环
        ]  # code

    # ── 写入缓存（内存 + 持久化） ──────────────────────────
    if file_hash:  # condition: file_hash:
        cache_key = make_cache_key(file_hash, standard, building_type)  # function call
        if len(_review_cache) >= _REVIEW_CACHE_MAX:  # check: numeric comparison
            old_key = next(iter(_review_cache))  # function call
            del _review_cache[old_key]  # code
        _review_cache[cache_key] = response_data  # assignment
        # 异步写入持久化缓存（不阻塞响应）
        _persistent_cache.set(cache_key, response_data, "review_result")  # function call

    return response_data  # return


@app.post("/batch-review")  # function call
async def batch_review(  # code
    files: List[UploadFile] = File(...),  # 操作
    building_type: str = Query(
        "civil", description="建筑类型: civil(民用) / industrial(工业)"
    ),  # function call
    building_types: Optional[List[str]] = Query(
        None, description="多建筑类型列表（混合建筑场景）"
    ),  # function call
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """多文件批量审查

    同时审查最多 20 个图纸文件，返回每个文件的单独审查结果，
    以及跨文件的交叉分析（同一违规类别在多少文件中出现）。
    """
    if len(files) < 1:  # check: numeric comparison
        raise HTTPException(
            status_code=400, detail={"status": "error", "message": "请至少上传一个文件"}
        )  # 抛出异常
    if len(files) > 20:  # check: numeric comparison
        raise HTTPException(
            status_code=400, detail={"status": "error", "message": "单次最多审查20个文件"}
        )  # 抛出异常

    start = time.time()  # get current time
    loop = asyncio.get_event_loop()  # function call
    from src.baa_engine.spec_repository import SpecRepository  # import
    from collections import Counter  # stdlib: collections

    repo = SpecRepository()  # function call
    registry_funcs = _func_registry.list_all()  # check all true

    results = []  # assignment
    all_details = []  # assignment
    all_entities = []  # assignment
    total_violations = 0  # assignment
    total_checks = 0  # assignment
    total_files = len(files)  # get length
    completed_files = 0  # assignment

    # ── 并发执行每个文件的审查（P37优化） ────────────────────
    async def _review_single_file(file: UploadFile) -> Dict:  # function call
        """单个文件审查（独立执行）"""
        nonlocal completed_files  # code
        async with _review_semaphore:  # code
            ext = (
                file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
            )  # function call
            if ext not in SUPPORTED_FORMATS:  # check: membership test
                completed_files += 1  # accumulate
                return {  # return: dict
                    "filename": file.filename,  # code
                    "status": "error",  # code
                    "error_code": "UNSUPPORTED_FORMAT",  # code
                    "message": f"不支持的文件格式: {ext}",  # code
                }  # code

            content = await file.read()  # function call
            if len(content) > MAX_FILE_SIZE:  # check: numeric comparison
                completed_files += 1  # accumulate
                return {  # return: dict
                    "filename": file.filename,  # code
                    "status": "error",  # code
                    "error_code": "FILE_TOO_LARGE",  # code
                    "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",  # get length
                }  # code

            file_id = generate_file_id()  # function call
            file_path = store_file(content, file_id, ext)  # function call

            # ── 解析（CPU密集型 → 线程池） ───────────────────
            result = await loop.run_in_executor(  # assignment
                ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id  # function call
            )  # code
            if not result.success:  # check: negated condition
                completed_files += 1  # accumulate
                return {  # return: dict
                    "filename": file.filename,  # code
                    "status": "error",  # code
                    "error_code": "PARSE_FAILED",  # code
                    "message": f"图纸解析失败: {result.error}",  # code
                }  # code

            # ── 语义分析（CPU密集型 → 线程池） ───────────────
            semantic = await loop.run_in_executor(  # assignment
                ENGINE_THREAD_POOL,  # code
                lambda: _semantic_analyzer.analyze(  # code
                    result.primitives,
                    result.dimensions,  # code
                    building_type=building_type,  # assignment
                ),  # code
            )  # code
            entities = semantic["entities"]  # assignment

            # 多建筑类型
            effective_types = building_types if building_types else [building_type]  # assignment

            # ── 规范判定 ──────────────────────────────────────
            details = []  # assignment
            found_entity_types = set(e["type"] for e in entities)  # function call

            def get_strict_threshold(
                clause_id: str,
            ) -> tuple:  # function: def get_strict_threshold(clause_id: str) -> tuple:
                worst_val, worst_unit, worst_op = None, None, None  # assignment
                for bt in effective_types:  # loop: iterate
                    v, u, o = repo.get_threshold(clause_id, bt)  # function call
                    if worst_val is None or v > worst_val:  # check: value is None
                        worst_val, worst_unit, worst_op = v, u, o  # assignment
                return worst_val, worst_unit, worst_op  # return

            for e in entities:  # loop: iterate
                for func in registry_funcs:  # loop: iterate
                    threshold_val, unit, op = get_strict_threshold(func.clause_id)  # function call
                    func.threshold = threshold_val  # assignment
                    func.unit = unit  # assignment
                    func.operator = op  # assignment
                    r = _func_registry.execute_with_timeout(func, e)  # function call
                    if r is None:  # check: value is None
                        continue  # code
                    if r.result != "PASS":  # condition: r.result != "PASS":
                        clause = {  # assignment
                            "standard": "GB50016",  # code
                            "clause_id": func.clause_id,  # code
                            "title": func.name,  # code
                            "text": func.description,  # code
                            "category": func.category.value,  # code
                        }  # code
                        f = _attribution_analyzer.build_finding(
                            r, clause, e, entities[:5]
                        )  # function call
                        details.append(
                            {  # code
                                "entity_id": e.get("id", e.get("type", "")),  # function call
                                "entity_type": e["type"],  # code
                                "clause_id": f.clause.get("clause_id", ""),  # function call
                                "clause_title": f.clause.get("title", ""),  # function call
                                "result": f.judgement["result"],  # code
                                "extracted_value": f.extracted_params["extracted_value"],  # code
                                "required_value": f.extracted_params.get(
                                    "required_value", 1.2
                                ),  # function call
                                "difference": f.extracted_params.get(
                                    "difference", 0
                                ),  # function call
                                "explanation": f.explanation[:120],  # code
                                "confidence": r.confidence,  # code
                                "severity": r.severity.value,  # code
                            }
                        )  # code

            # ── 缺失检查 ──────────────────────────────────────
            for func in registry_funcs:  # loop: iterate
                if func.category.value != "exist":  # check: OR condition
                    continue  # code
                has_match = any(func.matches(e) for e in entities)  # check any true
                if not has_match:  # check: negated condition
                    r = _func_registry.execute_with_timeout(func, None)  # function call
                    if r is not None and r.result != "PASS":  # check: value is not None
                        clause = {  # assignment
                            "standard": "GB50016",  # code
                            "clause_id": func.clause_id,  # code
                            "title": func.name,  # code
                            "text": func.description,  # code
                            "category": func.category.value,  # code
                        }  # code
                        f = _attribution_analyzer.build_finding(
                            r, clause, {}, entities[:5]
                        )  # function call
                        details.append(
                            {  # code
                                "entity_id": "",  # code
                                "entity_type": "missing",  # code
                                "clause_id": f.clause.get("clause_id", ""),  # function call
                                "clause_title": f.clause.get("title", ""),  # function call
                                "result": f.judgement["result"],  # code
                                "extracted_value": 0.0,  # code
                                "required_value": f.extracted_params.get(
                                    "required_value", 1.0
                                ),  # function call
                                "difference": -f.extracted_params.get(
                                    "required_value", 1.0
                                ),  # function call
                                "explanation": f.explanation[:120],  # code
                            }
                        )  # code

            # ── 单文件统计 ────────────────────────────────────
            entity_types = Counter(e["type"] for e in entities)  # function call
            violation_count = Counter(d["clause_id"] for d in details)  # function call

            # ── 评分（P36） ────────────────────────────────────
            score = 100.0  # assignment
            if details:  # condition: details:
                violation_deduction = len(details) * 5.0  # get length
                critical_count = sum(
                    1 for d in details if d.get("severity") == "critical"
                )  # aggregate sum
                major_count = sum(
                    1 for d in details if d.get("severity") == "major"
                )  # aggregate sum
                score = max(
                    0, 100.0 - violation_deduction - critical_count * 10 - major_count * 3
                )  # get maximum

            completed_files += 1  # accumulate
            return {  # return: dict
                "filename": file.filename,  # code
                "file_id": file_id,  # code
                "status": "success",  # code
                "summary": {  # code
                    "total_checks": len(entities) * len(registry_funcs),  # get length
                    "total_entities": len(entities),  # get length
                    "entity_types": dict(entity_types),  # function call
                    "violations": len(details),  # get length
                    "violation_by_clause": dict(violation_count.most_common(10)),  # function call
                    "score": score,  # code
                },  # code
                "details": details[:100],  # code
                "entities": [  # code
                    {
                        "id": e.get("id", e.get("type", "")),
                        "type": e["type"],
                        "bbox": e["bbox"],
                    }  # function call
                    for e in entities  # loop: iterate
                ],  # code
            }  # code

    # ── 并发执行所有文件 ──────────────────────────────────────
    file_tasks = [asyncio.create_task(_review_single_file(f)) for f in files]  # function call
    file_results = await asyncio.gather(*file_tasks)  # function call

    # 汇总变量
    all_details = []  # assignment
    all_entities_list = []  # assignment
    total_violations = 0  # assignment
    total_checks = 0  # assignment
    severity_counter = Counter()  # function call
    entity_type_counter = Counter()  # function call

    for file_result in file_results:  # loop: iterate
        if file_result["status"] == "success":  # condition: file_result["status"] == "success":
            total_violations += file_result["summary"]["violations"]  # accumulate
            total_checks += file_result["summary"]["total_checks"]  # accumulate
            all_details.extend(file_result["details"])  # extend list
            all_entities_list.extend(file_result.get("entities", []))  # extend list
            for d in file_result["details"]:  # loop: iterate
                severity_counter[d.get("severity", "major")] += 1  # function call
            for etype, count in (
                file_result["summary"].get("entity_types", {}).items()
            ):  # loop: iterate
                entity_type_counter[etype] += count  # accumulate

    # ── 交叉分析：跨图纸找出同一违规类别 ─────────────────────
    cross_clause = Counter(d["clause_id"] for d in all_details)  # function call
    cross_analysis = []  # assignment
    for clause_id, count in cross_clause.most_common(10):  # loop: iterate
        involved_files = set()  # function call
        for r in file_results:  # loop: iterate
            if r["status"] != "success":  # condition: r["status"] != "success":
                continue  # code
            for d in r["details"]:  # loop: iterate
                if d["clause_id"] == clause_id:  # condition: d["clause_id"] == clause_id:
                    involved_files.add(r["filename"])  # function call
                    break  # code
        cross_analysis.append(
            {  # code
                "clause_id": clause_id,  # code
                "violations": count,  # code
                "files": len(involved_files),  # get length
                "file_names": list(involved_files)[:5],  # function call
            }
        )  # code

    elapsed = int((time.time() - start) * 1000)  # get current time

    return {  # return: dict
        "status": "success",  # code
        "batch_summary": {  # code
            "total_files": len(files),  # get length
            "success_files": sum(
                1 for r in file_results if r["status"] == "success"
            ),  # aggregate sum
            "failed_files": sum(
                1 for r in file_results if r["status"] != "success"
            ),  # aggregate sum
            "total_violations": total_violations,  # code
            "total_checks": total_checks,  # code
            "total_entities": len(all_entities_list),  # get length
            "processing_time_ms": elapsed,  # code
            # 项目级统计
            "severity_distribution": dict(severity_counter),  # function call
            "entity_type_distribution": dict(entity_type_counter),  # function call
        },  # code
        "cross_analysis": cross_analysis,  # code
        "results": file_results,  # code
    }  # code


@app.post("/review-from-data")  # function call
async def review_from_data(  # code
    body: dict,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """从已解析的结构化数据执行规范审查（无需重新上传文件）

    接收前端或其他服务已解析好的实体数据，直接运行规范判定。
    适用于已有结构化数据的场景，跳过图纸解析步骤。
    """
    entities = body.get("entities", [])  # function call
    building_type = body.get("building_type", "civil")  # function call
    building_types = body.get("building_types")  # function call
    effective_types = building_types if building_types else [building_type]  # assignment

    from src.baa_engine.spec_repository import SpecRepository  # import
    from collections import Counter  # stdlib: collections

    repo = SpecRepository()  # function call
    clause_results = Counter()  # function call
    details = []  # assignment
    registry_funcs = _func_registry.list_all()  # check all true

    start = time.time()  # get current time

    # 多建筑类型并行匹配：取最严格阈值
    def get_strict_threshold(
        clause_id: str,
    ) -> tuple:  # function: def get_strict_threshold(clause_id: str) -> tuple:
        worst_val, worst_unit, worst_op = None, None, None  # assignment
        for bt in effective_types:  # loop: iterate
            v, u, o = repo.get_threshold(clause_id, bt)  # function call
            if worst_val is None or v > worst_val:  # check: value is None
                worst_val, worst_unit, worst_op = v, u, o  # assignment
        return worst_val, worst_unit, worst_op  # return

    # ── 逐实体逐函数规范判定 ──────────────────────────────
    for e in entities:  # 循环
        for func in registry_funcs:  # 循环
            threshold_val, unit, op = get_strict_threshold(func.clause_id)  # function call
            func.threshold = threshold_val  # assignment
            func.unit = unit  # assignment
            func.operator = op  # assignment
            r = _func_registry.execute_with_timeout(func, e)  # function call
            if r is None:  # check: value is None
                continue  # 继续循环
            clause_results[func.clause_id] += 1  # accumulate
            if r.result != "PASS":  # condition: r.result != "PASS":
                clause = {  # assignment
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # code
                f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])  # function call
                details.append(
                    {  # code
                        "entity_id": e.get("id", e.get("type", "")),  # 字段
                        "entity_type": e["type"],  # 字段
                        "clause_id": f.clause.get("clause_id", ""),  # 字段
                        "clause_title": f.clause.get("title", ""),  # 字段
                        "result": f.judgement["result"],  # 字段
                        "extracted_value": f.extracted_params["extracted_value"],  # 字段
                        "required_value": f.extracted_params.get("required_value", 1.2),  # 字段
                        "difference": f.extracted_params.get("difference", 0),  # 字段
                        "severity": f.judgement.get("severity", "major"),  # 字段
                        "explanation": f.explanation[:120],  # 字段
                    }
                )  # code

    # ── 缺失检查 ──────────────────────────────────────────
    for func in registry_funcs:  # 循环
        if func.category.value != "exist":  # check: OR condition
            continue  # 继续循环
        has_match = any(func.matches(e) for e in entities)  # check any true
        if not has_match:  # check: negated condition
            r = _func_registry.execute_with_timeout(func, None)  # function call
            if r is not None and r.result != "PASS":  # check: value is not None
                clause = {  # assignment
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # code
                f = _attribution_analyzer.build_finding(
                    r, clause, {}, entities[:5]
                )  # function call
                details.append(
                    {  # code
                        "entity_id": "",  # 字段
                        "entity_type": "missing",  # 字段
                        "clause_id": f.clause.get("clause_id", ""),  # 字段
                        "clause_title": f.clause.get("title", ""),  # 字段
                        "result": f.judgement["result"],  # 字段
                        "severity": "critical",  # 字段
                        "extracted_value": 0.0,  # 字段
                        "required_value": f.extracted_params.get("required_value", 1.0),  # 字段
                        "difference": -f.extracted_params.get("required_value", 1.0),  # 字段
                        "explanation": f.explanation[:120],  # 字段
                    }
                )  # code

    elapsed = int((time.time() - start) * 1000)  # get current time
    entity_types = Counter(e["type"] for e in entities)  # function call
    violation_count = Counter(d["clause_id"] for d in details)  # function call

    response_data = {  # assignment
        "status": "success",  # 字段
        "summary": {  # 字段
            "total_entities": len(entities),  # 字段
            "entity_types": dict(entity_types),  # 字段
            "total_checks": len(entities) * len(registry_funcs),  # 字段
            "violations": len(details),  # 字段
            "violation_by_clause": dict(violation_count.most_common(10)),  # 字段
        },  # code
        "details": details[:100],  # 字段
        "building_type": building_type,  # 字段
        "processing_time_ms": elapsed,  # 字段
    }  # code

    # ── 生成修正建议 ──────────────────────────────────────
    try:  # 尝试
        from src.baa_engine.correction_engine import CorrectionEngine  # import

        ce = CorrectionEngine()  # function call
        review_result_for_correction = {  # assignment
            "findings": [
                {  # 字段
                    "entity_id": d["entity_id"],  # 字段
                    "entity_type": d["entity_type"],  # 字段
                    "clause_id": d["clause_id"],  # 字段
                    "clause_title": d["clause_title"],  # 字段
                    "extracted_value": d["extracted_value"],  # 字段
                    "required_value": d["required_value"],  # 字段
                    "difference": d["difference"],  # 字段
                }
                for d in details
            ]  # code
        }  # code
        corrections = ce.generate_for_result(review_result_for_correction)  # function call
        response_data["corrections"] = corrections  # 操作
        # raw_result 供对比重构消费
        response_data["raw_result"] = {  # 操作
            "elements": elements,  # 字段
            "details": details,  # 字段
            "corrections": corrections,  # 字段
            "summary": response_data.get("summary", {}),  # 字段
        }  # code
    except Exception as e:  # 捕获异常
        response_data["corrections"] = []  # 操作
        response_data["raw_result"] = {"elements": elements, "details": details}  # 操作

    return response_data  # return


@app.post("/reconstruct")  # function call
async def reconstruct(  # code
    body: dict,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """BIM 重构（需授权验证）

    将已解析的审查结果重构为 IFC 格式的 BIM 模型文件。
    需要有效的 auth_token（通过支付获取）。
    """
    file_id = body.get("file_id", "")  # function call
    auth_token = body.get("auth_token", "")  # function call

    # ── 验证授权 ────────────────────────────────────────────
    auth_payload = verify_auth_token(auth_token)  # function call
    if auth_payload is None:  # check: value is None
        raise HTTPException(  # 抛出异常
            status_code=402,  # assignment
            detail={  # assignment
                "status": "error",  # 字段
                "error_code": "AUTH_FAILED",  # 字段
                "message": "支付授权验证失败，请确认订单已支付",  # 字段
            },  # code
        )  # code

    # ── 检查 file_id 是否存在 ───────────────────────────────
    file_path = get_file_path(file_id)  # function call
    if not file_path:  # check: negated condition
        raise HTTPException(  # 抛出异常
            status_code=404,  # assignment
            detail={  # assignment
                "status": "error",  # 字段
                "error_code": "FILE_NOT_FOUND",  # 字段
                "message": f"文件不存在: {file_id}",  # 字段
            },  # code
        )  # code

    # ── 执行重构（暂返回 mock 数据） ─────────────────────────
    order_id = f"baa-order-{uuid.uuid4().hex[:8]}"  # function call
    model_path = MODELS_DIR / order_id  # assignment
    model_path.mkdir(parents=True, exist_ok=True)  # function call
    (model_path / "model.ifc").write_text(  # 写入模型文件
        f"# Mock IFC file for order {order_id}\n"  # code
        f"# Generated from file: {file_id}\n"  # code
    )  # code

    base_url = str(app.root_path) if app.root_path else "http://localhost:8000"  # function call

    return {  # return: dict
        "status": "success",  # 字段
        "order_id": body.get("order_id", ""),  # 字段
        "baa_order_id": order_id,  # 字段
        "model_url": f"{base_url}/models/{order_id}/model.ifc",  # 字段
        "elements_count": 40,  # 字段
        "processing_time_ms": 15000,  # 字段
        "file_size_mb": 2.5,  # 字段
        "valid_until": (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z",  # 字段
    }  # code


@app.get("/order/{order_id}")  # function call
async def get_order(  # code
    order_id: str,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """订单状态查询

    查询 BIM 重构订单的处理状态和结果下载链接。
    """
    order_dir = MODELS_DIR / order_id  # assignment
    if not order_dir.exists():  # check: negated condition
        raise HTTPException(  # 抛出异常
            status_code=404,  # assignment
            detail={  # assignment
                "status": "error",  # 字段
                "error_code": "ORDER_NOT_FOUND",  # 字段
                "message": "订单不存在",  # 字段
            },  # code
        )  # code

    model_file = order_dir / "model.ifc"  # assignment
    if model_file.exists():  # condition: model_file.exists():
        return {  # return: dict
            "status": "completed",  # 字段
            "order_id": order_id,  # 字段
            "progress": 100,  # 字段
            "model_url": f"/models/{order_id}/model.ifc",  # 字段
            "file_size_mb": round(model_file.stat().st_size / 1024 / 1024, 2),  # 字段
        }  # code
    else:  # 否则
        return {  # return: dict
            "status": "processing",  # 字段
            "order_id": order_id,  # 字段
            "progress": 50,  # 字段
            "estimated_remaining_ms": 15000,  # 字段
        }  # code


# ── 图纸渲染 ──────────────────────────────────────────────


@app.get("/render/{file_id}")  # function call
async def render_drawing(  # code
    file_id: str,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """将 DXF/DWG 图纸渲染为 SVG 供前端展示

    从存储的 DWG/DXF 文件中提取图元，生成缩放适配的 SVG 预览图。
    支持 LINE、LWPOLYLINE、CIRCLE、TEXT/MTEXT 等图元类型。
    最多渲染 2000 个图元以避免超时。
    """
    file_path = get_file_path(file_id)  # function call
    if not file_path:  # check: negated condition
        raise HTTPException(
            status_code=404, detail={"status": "error", "message": "文件不存在"}
        )  # 抛出异常

    import ezdxf  # import
    from io import StringIO  # import

    # 异常保护：捕获可能失败的调用
    try:  # 尝试
        doc = ezdxf.readfile(str(file_path))  # function call
        msp = doc.modelspace()  # function call
    except Exception:  # 捕获异常
        raise HTTPException(
            status_code=400, detail={"status": "error", "message": "无法解析图纸文件"}
        )  # 抛出异常

    # ── 计算图元边界（用于 SVG viewBox 适配） ────────────────
    all_x, all_y = [], []  # assignment
    for entity in msp:  # 循环
        try:  # 尝试
            if entity.dxftype() == "LINE":  # condition: entity.dxftype() == "LINE":
                s, e = entity.dxf.start, entity.dxf.end  # assignment
                all_x.extend([s[0], e[0]])  # extend list
                all_y.extend([s[1], e[1]])  # extend list
            elif entity.dxftype() == "LWPOLYLINE":  # 分支
                pts = [(v[0], v[1]) for v in entity.get_points()]  # function call
                all_x.extend(p[0] for p in pts)  # extend list
                all_y.extend(p[1] for p in pts)  # extend list
            elif entity.dxftype() == "CIRCLE":  # 分支
                cx, cy = entity.dxf.center[:2]  # assignment
                r = entity.dxf.radius  # assignment
                all_x.extend([cx - r, cx + r])  # extend list
                all_y.extend([cy - r, cy + r])  # extend list
            elif entity.dxftype() in ("TEXT", "MTEXT"):  # 分支
                ins = entity.dxf.insert[:2]  # assignment
                all_x.append(ins[0])  # append to list
                all_y.append(ins[1])  # append to list
        except Exception:  # 捕获异常
            continue  # 继续循环

    # 根据条件判断分支：if not all_x
    if not all_x:  # check: negated condition
        return {"status": "error", "message": "图纸无有效图元"}  # return: dict

    # ── 计算 SVG viewBox 参数 ────────────────────────────────
    margin = 5.0  # assignment
    x_min, x_max = min(all_x) - margin, max(all_x) + margin  # 解包
    y_min, y_max = min(all_y) - margin, max(all_y) + margin  # 解包
    w, h = x_max - x_min, y_max - y_min  # assignment

    svg_w = min(max(w * 0.5, 400), 1200)  # SVG 输出宽度
    svg_h = min(max(h * 0.5, 300), 800)  # SVG 输出高度

    # ── 构建 SVG 字符串 ──────────────────────────────────────
    buf = StringIO()  # function call
    buf.write(
        f'<svg xmlns="http://www.w3.org/2000/svg" '  # assignment
        f'viewBox="{x_min} {-y_max} {w} {h}" '  # 操作
        f'width="{svg_w}" height="{svg_h}" '  # 操作
        f'style="background:#fff">\n'
    )  # assignment

    max_entities = 2000  # 渲染上限，避免大图纸超时
    drawn = 0  # assignment

    # 遍历处理
    for entity in msp:  # 循环
        if drawn >= max_entities:  # check: numeric comparison
            break  # 跳出循环
        dxftype = entity.dxftype()  # function call
        try:  # 尝试
            if dxftype == "LINE":  # condition: dxftype == "LINE":
                s, e = entity.dxf.start, entity.dxf.end  # assignment
                buf.write(
                    f'<line x1="{s[0]:.2f}" y1="{-s[1]:.2f}" '  # assignment
                    f'x2="{e[0]:.2f}" y2="{-e[1]:.2f}" '  # 操作
                    f'stroke="#333" stroke-width="0.5" />\n'
                )  # assignment
                drawn += 1  # accumulate
            elif dxftype == "LWPOLYLINE":  # 分支
                pts = [(v[0], -v[1]) for v in entity.get_points()]  # function call
                d = "M" + " L".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts)  # function call
                buf.write(
                    f'<path d="{d}" fill="none" stroke="#333" stroke-width="0.5" />\n'
                )  # function call
                drawn += 1  # accumulate
            elif dxftype == "CIRCLE":  # 分支
                cx, cy = entity.dxf.center[:2]  # assignment
                r = entity.dxf.radius  # assignment
                buf.write(
                    f'<circle cx="{cx:.2f}" cy="{-cy:.2f}" r="{r:.2f}" '  # assignment
                    f'fill="none" stroke="#333" stroke-width="0.5" />\n'
                )  # assignment
                drawn += 1  # accumulate
            elif dxftype in ("TEXT", "MTEXT"):  # 分支
                ins = entity.dxf.insert[:2]  # assignment
                txt = entity.dxf.text if hasattr(entity.dxf, "text") else ""  # attribute check
                ht = entity.dxf.height if hasattr(entity.dxf, "height") else 2.5  # attribute check
                buf.write(
                    f'<text x="{ins[0]:.2f}" y="{-ins[1]:.2f}" '  # assignment
                    f'font-size="{ht}" fill="#666">{txt[:30]}</text>\n'
                )  # assignment
                drawn += 1  # accumulate
        except Exception:  # 捕获异常
            continue  # 继续循环

    buf.write("</svg>")  # function call
    svg_content = buf.getvalue()  # function call

    return Response(content=svg_content, media_type="image/svg+xml")  # return


# ── PDF 审查报告导出 ─────────────────────────────────


@app.get("/review/{file_id}/pdf")  # function call
# ── 项目级审查汇总 ─────────────────────────────────────


@app.get("/review/project/summary")
async def project_summary(
    file_ids: List[str] = Query(..., description="待汇总的文件ID列表（已审查过的文件）"),
    api_key: str = Depends(verify_api_key),
):
    """项目级审查汇总

    对已审查过的多个图纸文件生成跨文件的统一汇总报告，
    包含项目总体评分、合规率、严重级别分布、规范条目热力图、
    项目级风险识别等维度。

    不重新审查，从缓存读取各文件审查结果后聚合。
    """
    from src.baa_engine.project_summary import (
        aggregate_project_summary,
        format_project_report,
    )

    if not file_ids:
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": "file_ids 不能为空"},
        )
    if len(file_ids) > 50:
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": "单次最多汇总50个文件"},
        )

    # ── 从缓存读取各文件审查结果 ───────────────────────────
    file_results = []
    for file_id in file_ids:
        # 先尝试从 PersistentCache 读取
        from src.baa_engine.cache import get_cache

        cached = get_cache().get(f"project_summary:{file_id}", "review_result")
        if cached and isinstance(cached, dict):
            file_results.append(cached)
            continue

        # 回退：尝试读取 drawing_parser 缓存中的审查结果
        # 如果缓存未命中，该文件不计入汇总
        file_results.append(
            {
                "filename": file_id,
                "status": "missing",
                "message": f"文件 {file_id} 的审查结果未缓存",
            }
        )

    # ── 聚合汇总 ──────────────────────────────────────────
    summary = aggregate_project_summary(file_results)
    report_text = format_project_report(summary)

    return {
        "status": "success",
        "summary": summary,
        "report_text": report_text,
    }


# ── 单文件 PDF 审查报告导出 ─────────────────────────────


async def review_pdf(  # code
    file_id: str,  # code
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """导出审查报告 PDF

    对已审查过的图纸生成结构化 PDF 审查报告，包含封面、
    违规分类统计、每条违规详情及修正建议。
    """
    from src.baa_engine.report_generator import ReviewReport  # import

    # 获取文件路径
    file_path = get_file_path(file_id)  # function call
    if not file_path:  # check: negated condition
        raise HTTPException(
            status_code=404, detail={"status": "error", "message": "文件不存在"}
        )  # function call

    # 重新审查（保证使用最新引擎版本）
    import asyncio  # stdlib: async

    loop = asyncio.get_event_loop()  # function call

    result = await loop.run_in_executor(  # assignment
        ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id  # function call
    )  # code
    if not result.success:  # check: negated condition
        raise HTTPException(
            status_code=400, detail={"status": "error", "message": f"图纸解析失败: {result.error}"}
        )  # function call

    semantic = await loop.run_in_executor(  # assignment
        ENGINE_THREAD_POOL,  # code
        lambda: _semantic_analyzer.analyze(
            result.primitives, result.dimensions, dxf_path=str(file_path)
        ),  # function call
    )  # code
    entities = semantic["entities"]  # assignment

    from src.baa_engine.spec_repository import SpecRepository  # import
    from collections import Counter  # stdlib: collections

    repo = SpecRepository()  # function call
    details = []  # assignment
    registry_funcs = _func_registry.list_all()  # check all true

    start = time.time()  # get current time

    # ── 逐实体逐函数规范判定 ──────────────────────────────
    for e in entities:  # loop: iterate
        for func in registry_funcs:  # loop: iterate
            threshold_val, unit, op = repo.get_threshold(func.clause_id, "civil")  # function call
            try:  # try block
                r = _func_registry.execute_with_timeout(func, e)  # function call
                if r is None:  # check: value is None
                    continue  # code
                clause = {  # assignment
                    "standard": "GB50016",  # code
                    "clause_id": func.clause_id,  # code
                    "title": func.name,  # code
                    "text": func.description,  # code
                    "category": func.category.value,  # code
                }  # code
                f = _attribution_analyzer.build_finding(
                    r, clause, {}, entities[:5]
                )  # function call
                if f.judgement["result"] != "PASS":  # condition: f.judgement["result"] != "PASS":
                    details.append(
                        {  # code
                            "entity_id": e.get("id", ""),  # function call
                            "entity_type": e.get("type", ""),  # function call
                            "clause_id": f.clause.get("clause_id", ""),  # function call
                            "clause_title": f.clause.get("title", ""),  # function call
                            "result": f.judgement["result"],  # code
                            "extracted_value": r.actual,  # code
                            "required_value": threshold_val,  # code
                            "difference": (r.actual or 0) - threshold_val,  # function call
                            "explanation": f.explanation[:120],  # code
                        }
                    )  # code
            except Exception:  # catch exception
                continue  # code

    # ── 缺失检查 ──────────────────────────────────────────
    for func in registry_funcs:  # loop: iterate
        if func.category.value != "exist":  # check: OR condition
            continue  # code
        has_match = any(func.matches(e) for e in entities)  # check any true
        if not has_match:  # check: negated condition
            r = _func_registry.execute_with_timeout(func, None)  # function call
            if r is not None and r.result != "PASS":  # check: value is not None
                clause = {  # assignment
                    "standard": "GB50016",  # code
                    "clause_id": func.clause_id,  # code
                    "title": func.name,  # code
                    "text": func.description,  # code
                    "category": func.category.value,  # code
                }  # code
                f = _attribution_analyzer.build_finding(
                    r, clause, {}, entities[:5]
                )  # function call
                details.append(
                    {  # code
                        "entity_id": "",  # code
                        "entity_type": "missing",  # code
                        "clause_id": f.clause.get("clause_id", ""),  # function call
                        "clause_title": f.clause.get("title", ""),  # function call
                        "result": f.judgement["result"],  # code
                        "extracted_value": 0.0,  # code
                        "required_value": f.extracted_params.get(
                            "required_value", 1.0
                        ),  # function call
                        "difference": -f.extracted_params.get(
                            "required_value", 1.0
                        ),  # function call
                        "explanation": f.explanation[:120],  # code
                    }
                )  # code

    elapsed = int((time.time() - start) * 1000)  # get current time
    entity_types = Counter(e["type"] for e in entities)  # function call
    violation_count = Counter(d["clause_id"] for d in details)  # function call

    summary = {  # assignment
        "total_entities": len(entities),  # get length
        "entity_types": dict(entity_types),  # function call
        "total_checks": len(entities) * len(registry_funcs),  # get length
        "violations": len(details),  # get length
        "violation_by_clause": dict(violation_count.most_common(10)),  # function call
        "building_type": "civil",  # code
        "processing_time_ms": elapsed,  # code
    }  # code

    # ── 修正建议 ──────────────────────────────────────────
    corrections = []  # assignment
    try:  # try block
        from src.baa_engine.correction_engine import CorrectionEngine  # import

        correction_engine = CorrectionEngine()  # function call
        review_result = {  # assignment
            "findings": [
                {  # code
                    "entity_id": d["entity_id"],  # code
                    "entity_type": d["entity_type"],  # code
                    "clause_id": d["clause_id"],  # code
                    "clause_title": d["clause_title"],  # code
                    "extracted_value": d["extracted_value"],  # code
                    "required_value": d["required_value"],  # code
                    "difference": d["difference"],  # code
                }
                for d in details
            ]  # code
        }  # code
        corrections = correction_engine.generate_for_result(review_result)  # function call
    except Exception:  # catch exception
        pass  # code

    # ── 生成 PDF ──────────────────────────────────────────
    generator = ReviewReport()  # function call
    pdf_bytes = generator.generate(  # assignment
        filename=file_path.name,  # assignment
        summary=summary,  # assignment
        details=details,  # assignment
        corrections=corrections,  # assignment
    )  # code

    return Response(  # return
        content=pdf_bytes,  # assignment
        media_type="application/pdf",  # assignment
        headers={  # assignment
            "Content-Disposition": f'attachment; filename="{file_path.stem}_report.pdf"',  # assignment
            "Content-Length": str(len(pdf_bytes)),  # get length
        },  # code
    )  # code


# ── 静态文件服务（模型下载） ─────────────────────────────

SPECS_DIR = DATA_DIR / "specs"  # assignment

if SPECS_DIR.exists():  # condition: SPECS_DIR.exists():
    app.mount("/data/specs", StaticFiles(directory=str(SPECS_DIR)), name="specs")  # function call

# 根据条件判断分支：if MODELS_DIR.exists()
if MODELS_DIR.exists():  # condition: MODELS_DIR.exists():
    app.mount("/models", StaticFiles(directory=str(MODELS_DIR)), name="models")  # function call


# ── API密钥管理端点 ──────────────────────────────────


@app.post("/admin/keys", tags=["admin"])  # function call
async def create_api_key(  # code
    body: dict,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
    _admin: str = Depends(require_admin),  # function call
):  # code
    """创建新的API Key（需要admin权限）"""
    km = get_key_manager()  # function call

    permission = body.get("permission", "write")  # function call
    ttl_days = body.get("ttl_days", 90)  # function call
    label = body.get("label", "")  # function call

    # 异常保护：捕获可能失败的调用
    try:  # 尝试
        result = km.generate_key(  # assignment
            permission=permission,  # assignment
            ttl_days=ttl_days,  # assignment
            label=label,  # assignment
            created_by=api_key or "anonymous",  # assignment
        )  # code
    except ValueError as e:  # 捕获异常
        raise HTTPException(
            status_code=400,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "INVALID_PARAM",  # 字段
                "message": str(e),  # 字段
            },
        )  # code

    return {  # return: dict
        "status": "success",  # 字段
        "data": result,  # 字段
        "warning": "请立即保存 raw_key，创建后不再显示",  # 字段
    }  # code


@app.get("/admin/keys", tags=["admin"])  # function call
async def list_api_keys(  # code
    include_disabled: bool = Query(False),  # function call
    include_raw: bool = Query(
        False, description="是否返回解密后的 raw_key（密钥详情时使用）"
    ),  # function call
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
    _admin: str = Depends(require_admin),  # function call
):  # code
    """列出所有API Key"""
    km = get_key_manager()  # function call
    keys = km.list_keys(include_disabled=include_disabled, include_raw=include_raw)  # function call
    stats = km.get_usage_stats()  # function call

    # 遍历处理
    for k in keys:  # 循环
        k_id = k["key_id"]  # assignment
        if k_id in stats:  # check: membership test
            k["usage"] = stats[k_id]  # 操作

    return {  # return: dict
        "status": "success",  # 字段
        "data": keys,  # 字段
        "total": len(keys),  # 字段
    }  # code


@app.get("/admin/keys/stats", tags=["admin"])  # function call
async def api_key_stats(  # code
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
    _admin: str = Depends(require_admin),  # function call
):  # code
    """API Key用量统计"""
    km = get_key_manager()  # function call

    stats = km.get_usage_stats()  # function call
    keys = km.list_keys(include_disabled=True)  # function call

    return {  # return: dict
        "status": "success",  # 字段
        "data": {  # 字段
            "keys": stats,  # 字段
            "summary": {  # 字段
                "total": len(keys),  # 字段
                "active": len([k for k in keys if k.get("enabled")]),  # 字段
                "disabled": len([k for k in keys if not k.get("enabled")]),  # 字段
                "total_calls": sum(s.get("total_calls", 0) for s in stats.values()),  # 字段
            },  # code
        },  # code
    }  # code


@app.get("/admin/keys/{key_id}", tags=["admin"])  # function call
async def get_api_key_detail(  # code
    key_id: str,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
    _admin: str = Depends(require_admin),  # function call
):  # code
    """获取单个API Key详情（含解密后的 raw_key）"""
    km = get_key_manager()  # function call
    keys = km.list_keys(include_disabled=True, include_raw=True)  # function call
    for k in keys:  # 循环
        if k["key_id"] == key_id:  # condition: k["key_id"] == key_id:
            stats = km.get_usage_stats(key_id)  # function call
            k["usage"] = stats  # 操作
            return {"status": "success", "data": k}  # return: dict
    raise HTTPException(
        status_code=404,
        detail={  # 抛出异常
            "status": "error",
            "error_code": "NOT_FOUND",  # 字段
            "message": f"密钥不存在: {key_id}",  # 字段
        },
    )  # code


@app.post("/admin/keys/{key_id}/revoke", tags=["admin"])  # function call
async def revoke_api_key(  # code
    key_id: str,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
    _admin: str = Depends(require_admin),  # function call
):  # code
    """撤销API Key"""
    km = get_key_manager()  # function call

    # 根据条件判断分支：if km.revoke_key(key_id)
    if km.revoke_key(key_id):  # condition: km.revoke_key(key_id):
        return {"status": "success", "message": f"密钥 {key_id} 已撤销"}  # return: dict
    raise HTTPException(
        status_code=404,
        detail={  # 抛出异常
            "status": "error",
            "error_code": "NOT_FOUND",  # 字段
            "message": f"密钥不存在: {key_id}",  # 字段
        },
    )  # code


@app.post("/admin/keys/{key_id}/rotate", tags=["admin"])  # function call
async def rotate_api_key(  # code
    key_id: str,  # 操作
    body: dict,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
    _admin: str = Depends(require_admin),  # function call
):  # code
    """轮换API Key（生成新密钥值，旧密钥失效）"""
    km = get_key_manager()  # function call
    result = km.rotate_key(key_id, new_ttl_days=new_ttl)  # function call
    if result:  # condition: result:
        return {  # return: dict
            "status": "success",  # 字段
            "data": result,  # 字段
            "warning": "旧密钥已失效，请立即保存新 raw_key",  # 字段
        }  # code
    raise HTTPException(
        status_code=404,
        detail={  # 抛出异常
            "status": "error",
            "error_code": "NOT_FOUND",  # 字段
            "message": f"密钥不存在或已禁用: {key_id}",  # 字段
        },
    )  # code


@app.delete("/admin/keys/{key_id}", tags=["admin"])  # function call
async def delete_api_key(  # code
    key_id: str,  # 操作
    request: Request = None,  # assignment
    api_key: str = Depends(verify_api_key),  # function call
    _admin: str = Depends(require_admin),  # function call
):  # code
    """物理删除API Key（不可恢复）"""
    km = get_key_manager()  # function call
    if km.delete_key(key_id):  # condition: km.delete_key(key_id):
        return {"status": "success", "message": f"密钥 {key_id} 已永久删除"}  # return: dict
    raise HTTPException(
        status_code=404,
        detail={  # 抛出异常
            "status": "error",
            "error_code": "NOT_FOUND",  # 字段
            "message": f"密钥不存在: {key_id}",  # 字段
        },
    )  # code


@app.post("/admin/keys/verify", tags=["admin"])  # function call
async def verify_api_key_raw(  # code
    body: dict,  # 操作
    request: Request = None,  # assignment
):  # code
    """验证原始API Key是否有效（无需admin权限，供前端导入时校验）"""
    raw_key = body.get("raw_key", "")  # function call
    if not raw_key:  # check: negated condition
        return {"status": "error", "valid": False, "message": "请提供 raw_key"}  # return: dict

    km = get_key_manager()  # function call
    key_info = km.validate_key(raw_key)  # function call
    if key_info and key_info.get("enabled", True):  # check: AND condition
        return {  # return: dict
            "status": "success",  # 字段
            "valid": True,  # 字段
            "key_info": {  # 字段
                "key_id": key_info.get("key_id"),  # 字段
                "label": key_info.get("label"),  # 字段
                "permission": key_info.get("permission"),  # 字段
                "expires_at": key_info.get("expires_at"),  # 字段
                "created_at": key_info.get("created_at"),  # 字段
            },  # code
        }  # code
    else:  # 否则
        return {  # return: dict
            "status": "success",  # 字段
            "valid": False,  # 字段
            "message": "密钥无效或已过期/撤销",  # 字段
        }  # code


@app.get("/admin/bootstrap-key", tags=["admin"])  # function call
async def bootstrap_admin_key():  # function call
    """获取前端密钥管理页使用的管理令牌（免认证）

    开发模式（BAA_API_KEY 未设置）时返回空字符串，
    此时后端 require_admin 不校验令牌，前端直接发请求即可。
    生产模式时返回环境变量中的 admin key。
    """
    env_key = os.getenv("BAA_API_KEY", "")  # function call
    return {  # return: dict
        "status": "success",  # 字段
        "admin_key": env_key,  # 字段
        "mode": "production" if env_key else "development",  # 字段
    }  # code


# ── EMA2 第三方对接 API ───────────────────────────────────


async def _fire_webhook(webhook_url: str, payload: dict) -> bool:  # function call
    """发送 Webhook 回调通知（异步，不阻塞主流程）

    Args:
        webhook_url: 回调目标 URL
        payload: 发送的 JSON 数据

    Returns:
        bool: 是否发送成功
    """
    import httpx  # import

    try:  # 尝试
        async with httpx.AsyncClient(timeout=10.0) as client:  # function call
            resp = await client.post(webhook_url, json=payload)  # function call
            return resp.status_code == 200  # return
    # 异常处理
    except Exception:  # 捕获异常
        return False  # return: boolean


async def _run_review_task(
    task_id: str, file_path: str, building_type: str, webhook_url: str = None
):  # function call
    """后台执行异步审查任务

    在后台线程中执行完整的审查流程：解析→语义分析→规范判定→缺失检查。
    完成后更新 _tasks 存储中的状态，并根据配置触发 Webhook 回调。
    """
    _tasks[task_id]["status"] = "running"  # 操作
    _tasks[task_id]["updated_at"] = datetime.now().isoformat()  # 操作

    # 异常保护：捕获可能失败的调用
    try:  # 尝试
        start = time.time()  # get current time
        loop = asyncio.get_event_loop()  # function call

        # ── Step 1: 图纸解析 ─────────────────────────────────
        result = await loop.run_in_executor(  # assignment
            ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), task_id  # 操作
        )  # code
        if not result.success:  # check: negated condition
            _tasks[task_id]["status"] = "failed"  # 操作
            _tasks[task_id]["error"] = f"解析失败: {result.error}"  # 操作
            _tasks[task_id]["updated_at"] = datetime.now().isoformat()  # 操作
            if webhook_url:  # condition: webhook_url:
                await _fire_webhook(
                    webhook_url,
                    {  # 操作
                        "task_id": task_id,
                        "status": "failed",
                        "error": _tasks[task_id]["error"],  # 字段
                    },
                )  # code
            return  # code

        # ── Step 2: 语义分析 ─────────────────────────────────
        semantic = await loop.run_in_executor(  # assignment
            ENGINE_THREAD_POOL,  # 解包
            lambda: _semantic_analyzer.analyze(  # 操作
                result.primitives, result.dimensions, building_type=building_type  # 解包
            ),  # code
        )  # code
        entities = semantic["entities"]  # assignment

        # ── Step 3: 规范判定 ─────────────────────────────────
        details = []  # assignment
        for e in entities:  # 循环
            for func in _func_registry.list_all():  # 循环
                threshold_val, unit, op = _spec_repo.get_threshold(
                    func.clause_id, building_type
                )  # function call
                func.threshold = threshold_val  # assignment
                func.unit = unit  # assignment
                func.operator = op  # assignment
                r = _func_registry.execute_with_timeout(func, e)  # function call
                if r is None or r.result == "PASS":  # check: value is None
                    continue  # 继续循环
                clause = {  # assignment
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # code
                f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])  # function call
                details.append(
                    {  # code
                        "entity_id": e.get("id", e.get("type", "")),  # 字段
                        "entity_type": e["type"],  # 字段
                        "clause_id": f.clause.get("clause_id", ""),  # 字段
                        "clause_title": f.clause.get("title", ""),  # 字段
                        "result": f.judgement["result"],  # 字段
                        "extracted_value": f.extracted_params["extracted_value"],  # 字段
                        "required_value": f.extracted_params.get("required_value", 1.2),  # 字段
                        "difference": f.extracted_params.get("difference", 0),  # 字段
                        "explanation": f.explanation[:120],  # 字段
                        "severity": f.judgement.get("severity", "major"),  # 字段
                    }
                )  # code

        # ── Step 4: 缺失检查 ─────────────────────────────────
        for func in _func_registry.list_all():  # 循环
            if func.category.value != "exist":  # check: OR condition
                continue  # 继续循环
            if not any(func.matches(e) for e in entities):  # check: membership test
                r = _func_registry.execute_with_timeout(func, None)  # function call
                if r is not None and r.result != "PASS":  # check: value is not None
                    clause = {  # assignment
                        "standard": "GB50016",  # 字段
                        "clause_id": func.clause_id,  # 字段
                        "title": func.name,  # 字段
                        "text": func.description,  # 字段
                        "category": func.category.value,  # 字段
                    }  # code
                    f = _attribution_analyzer.build_finding(
                        r, clause, {}, entities[:5]
                    )  # function call
                    details.append(
                        {  # code
                            "entity_id": "",  # 字段
                            "entity_type": "missing",  # 字段
                            "clause_id": f.clause.get("clause_id", ""),  # 字段
                            "clause_title": f.clause.get("title", ""),  # 字段
                            "result": f.judgement["result"],  # 字段
                            "extracted_value": 0.0,  # 字段
                            "required_value": f.extracted_params.get("required_value", 1.0),  # 字段
                            "difference": -f.extracted_params.get("required_value", 1.0),  # 字段
                            "explanation": f.explanation[:120],  # 字段
                            "severity": f.judgement.get("severity", "major"),  # 字段
                        }
                    )  # code

        elapsed = int((time.time() - start) * 1000)  # get current time

        # ── 存储结果 ────────────────────────────────────────
        _tasks[task_id]["status"] = "completed"  # 操作
        _tasks[task_id]["result"] = {  # 操作
            "summary": {  # 字段
                "total_entities": len(entities),  # 字段
                "violations": len(details),  # 字段
                "entity_types": dict(Counter(e["type"] for e in entities)),  # 字段
            },  # code
            "details": details,  # 字段
            "processing_time_ms": elapsed,  # 字段
        }  # code
        _tasks[task_id]["updated_at"] = datetime.now().isoformat()  # 操作

        # ── Webhook 回调通知 ─────────────────────────────────
        if webhook_url:  # condition: webhook_url:
            await _fire_webhook(
                webhook_url,
                {  # 操作
                    "task_id": task_id,
                    "status": "completed",  # 字段
                    "violations": len(details),
                    "entities": len(entities),  # 字段
                    "processing_time_ms": elapsed,  # 字段
                },
            )  # code

    # 异常处理
    except Exception as e:  # 捕获异常
        _tasks[task_id]["status"] = "failed"  # 操作
        _tasks[task_id]["error"] = str(e)  # 操作
        _tasks[task_id]["updated_at"] = datetime.now().isoformat()  # 操作
        if webhook_url:  # condition: webhook_url:
            await _fire_webhook(
                webhook_url,
                {"task_id": task_id, "status": "failed", "error": str(e)},  # 操作  # 字段
            )  # code


@app.post("/api/v1/tasks", tags=["EMA2"])  # function call
async def create_review_task(  # code
    file: UploadFile = File(...),  # function call
    building_type: str = Query("civil", description="建筑类型: civil/industrial"),  # function call
    webhook_url: str = Query("", description="回调通知 URL（可选）"),  # function call
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """创建异步审查任务（EMA2 对接）

    上传图纸文件，创建异步审查任务。任务完成后通过轮询或 Webhook 获取结果。
    """
    filename = file.filename or "unknown"  # assignment
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""  # function call
    if ext not in SUPPORTED_FORMATS:  # check: membership test
        raise HTTPException(
            status_code=400,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "UNSUPPORTED_FORMAT",  # 字段
                "message": f"不支持的文件格式: {ext}",  # 字段
            },
        )  # code

    content = await file.read()  # function call
    if len(content) > MAX_FILE_SIZE:  # check: numeric comparison
        raise HTTPException(
            status_code=400,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "FILE_TOO_LARGE",  # 字段
                "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",  # 字段
            },
        )  # code

    file_id = generate_file_id()  # function call
    file_path = store_file(content, file_id, ext)  # function call

    # 创建任务
    task_id = str(uuid.uuid4())[:8]  # function call
    _tasks[task_id] = {  # assignment
        "task_id": task_id,  # 字段
        "status": "pending",  # 字段
        "file_id": file_id,  # 字段
        "file_path": str(file_path),  # 字段
        "filename": filename,  # 字段
        "building_type": building_type,  # 字段
        "webhook_url": webhook_url or None,  # 字段
        "created_at": datetime.now().isoformat(),  # 字段
        "updated_at": datetime.now().isoformat(),  # 字段
        "result": None,  # 字段
        "error": None,  # 字段
    }  # code

    # 启动后台任务
    asyncio.create_task(
        _run_review_task(task_id, str(file_path), building_type, webhook_url)
    )  # function call

    return {  # return: dict
        "status": "success",  # 字段
        "task_id": task_id,  # 字段
        "status_url": f"/api/v1/tasks/{task_id}",  # 字段
        "result_url": f"/api/v1/tasks/{task_id}/result",  # 字段
    }  # code


@app.get("/api/v1/tasks/{task_id}", tags=["EMA2"])  # function call
async def get_task_status(task_id: str, api_key: str = Depends(verify_api_key)):  # function call
    """查询任务状态（EMA2 对接）"""
    task = _tasks.get(task_id)  # function call
    if not task:  # check: negated condition
        raise HTTPException(
            status_code=404,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "TASK_NOT_FOUND",  # 字段
                "message": f"任务不存在: {task_id}",  # 字段
            },
        )  # code

    return {  # return: dict
        "status": "success",  # 字段
        "task_id": task_id,  # 字段
        "state": task["status"],  # 字段
        "filename": task.get("filename"),  # 字段
        "created_at": task.get("created_at"),  # 字段
        "updated_at": task.get("updated_at"),  # 字段
        "error": task.get("error"),  # 字段
    }  # code


@app.get("/api/v1/tasks/{task_id}/result", tags=["EMA2"])  # function call
async def get_task_result(task_id: str, api_key: str = Depends(verify_api_key)):  # function call
    """获取审查结果（EMA2 对接）"""
    task = _tasks.get(task_id)  # function call
    if not task:  # check: negated condition
        raise HTTPException(
            status_code=404,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "TASK_NOT_FOUND",  # 字段
                "message": f"任务不存在: {task_id}",  # 字段
            },
        )  # code

    # 根据条件判断分支：if task["status"] == "pending"
    if task["status"] == "pending":  # condition: task["status"] == "pending":
        raise HTTPException(
            status_code=409,
            detail={  # 抛出异常
                "status": "pending",  # 字段
                "message": "任务仍在处理中，请稍后查询",  # 字段
            },
        )  # code

    # 根据条件判断分支：if task["status"] == "failed"
    if task["status"] == "failed":  # condition: task["status"] == "failed":
        raise HTTPException(
            status_code=500,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "TASK_FAILED",  # 字段
                "message": task.get("error", "任务执行失败"),  # 字段
            },
        )  # code

    return {  # return: dict
        "status": "success",  # 字段
        "task_id": task_id,  # 字段
        "result": task.get("result"),  # 字段
    }  # code


@app.post("/api/v1/webhooks", tags=["EMA2"])  # function call
async def register_webhook(  # code
    url: str = Query(..., description="回调 URL"),  # function call
    events: str = Query("completed", description="触发事件: completed,failed,all"),  # function call
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """注册 Webhook 回调（EMA2 对接）

    注册后，当异步审查任务完成或失败时，系统会 POST 通知到该 URL。
    """
    webhook_id = str(uuid.uuid4())[:8]  # function call
    _webhooks[webhook_id] = {  # assignment
        "webhook_id": webhook_id,  # 字段
        "url": url,  # 字段
        "events": events,  # 字段
        "active": True,  # 字段
        "created_at": datetime.now().isoformat(),  # 字段
    }  # code
    return {  # return: dict
        "status": "success",  # 字段
        "webhook_id": webhook_id,  # 字段
        "url": url,  # 字段
        "events": events,  # 字段
    }  # code


@app.get("/api/v1/webhooks", tags=["EMA2"])  # function call
async def list_webhooks(api_key: str = Depends(verify_api_key)):  # function call
    """查询 Webhook 列表（EMA2 对接）"""
    return {  # return: dict
        "status": "success",  # 字段
        "webhooks": list(_webhooks.values()),  # 字段
    }  # code


@app.delete("/api/v1/webhooks/{webhook_id}", tags=["EMA2"])  # function call
async def delete_webhook(webhook_id: str, api_key: str = Depends(verify_api_key)):  # function call
    """删除 Webhook（EMA2 对接）"""
    if webhook_id not in _webhooks:  # check: membership test
        raise HTTPException(
            status_code=404,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "WEBHOOK_NOT_FOUND",  # 字段
                "message": f"Webhook 不存在: {webhook_id}",  # 字段
            },
        )  # code
    del _webhooks[webhook_id]  # 删除
    return {"status": "success", "message": "Webhook 已删除"}  # return: dict


# ── P10 反馈闭环 API ───────────────────────────────────────


@app.post("/api/v1/feedbacks", tags=["Feedback"])  # function call
async def submit_feedback(body: dict):  # function call
    """提交违规申诉（P10 反馈闭环）

    用户对审查结果有异议时，提交申诉。
    Body 包含 task_id, clause_id, entity_id, entity_type, reason, description 等。
    申诉数据后续用于模型微调，减少误报。
    """
    record = _feedback_manager.submit(  # assignment
        task_id=body.get("task_id", ""),  # function call
        clause_id=body.get("clause_id", ""),  # function call
        entity_id=body.get("entity_id", ""),  # function call
        entity_type=body.get("entity_type", ""),  # function call
        reason=body.get("reason", ""),  # function call
        description=body.get("description", ""),  # function call
        original_value=body.get("original_value"),  # function call
        severity=body.get("severity", ""),  # function call
    )  # code
    return {"status": "success", "feedback": record}  # return: dict


@app.get("/api/v1/feedbacks", tags=["Feedback"])  # function call
async def list_feedbacks(  # code
    status: str = Query("", description="筛选状态: pending/accepted/rejected"),  # function call
    clause_id: str = Query("", description="筛选规范条款"),  # function call
    limit: int = Query(50, ge=1, le=200),  # function call
    offset: int = Query(0, ge=0),  # function call
):  # code
    """查询申诉列表（支持状态和规范条款筛选）"""
    items, total = _feedback_manager.list_all(  # assignment
        status=status, clause_id=clause_id, limit=limit, offset=offset  # assignment
    )  # code
    return {"status": "success", "feedbacks": items, "total": total}  # return: dict


@app.get("/api/v1/feedbacks/stats", tags=["Feedback"])  # function call
async def feedback_stats():  # function call
    """申诉统计（总数、待处理数、各类分布）"""
    return {"status": "success", "stats": _feedback_manager.stats()}  # return: dict


@app.get("/api/v1/feedbacks/{feedback_id}", tags=["Feedback"])  # function call
async def get_feedback(feedback_id: str):  # function call
    """查询单条申诉详情"""
    record = _feedback_manager.get(feedback_id)  # function call
    if not record:  # check: negated condition
        raise HTTPException(
            status_code=404,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "FEEDBACK_NOT_FOUND",  # 字段
                "message": f"申诉不存在: {feedback_id}",  # 字段
            },
        )  # code
    return {"status": "success", "feedback": record}  # return: dict


@app.patch("/api/v1/feedbacks/{feedback_id}", tags=["Feedback"])  # function call
async def review_feedback(  # code
    feedback_id: str,  # 操作
    body: dict,  # 操作
):  # code
    """审核申诉（P10 反馈闭环）

    管理员审核用户提交的申诉。
    Body: {status: accepted/rejected, reviewed_by, review_comment?}
    """
    record = _feedback_manager.review(  # assignment
        feedback_id,
        body.get("status", ""),
        body.get("reviewed_by", ""),  # 操作
        body.get("review_comment", ""),  # function call
    )  # code
    if not record:  # check: negated condition
        raise HTTPException(
            status_code=404,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "FEEDBACK_NOT_FOUND",  # 字段
                "message": f"申诉不存在: {feedback_id}",  # 字段
            },
        )  # code
    return {"status": "success", "feedback": record}  # return: dict


@app.post("/api/v1/feedbacks/{feedback_id}/adjust", tags=["Feedback"])  # function call
async def adjust_threshold(  # code
    feedback_id: str,  # 操作
    body: dict,  # 操作
):  # code
    """基于申诉数据计算/应用阈值调整

    使用 LearningEngine 分析申诉数据，计算建议的阈值调整值。
    如果 apply=true，直接应用调整到规范知识库。
    Body: {clause_id, apply?}
    """
    clause_id = body.get("clause_id", "")  # function call
    apply = body.get("apply", False)  # function call

    # 异常保护：捕获可能失败的调用
    try:  # 尝试
        current, unit, op = _spec_repo.get_threshold(clause_id, "civil")  # 操作
    except ValueError:  # 捕获异常
        raise HTTPException(
            status_code=404,
            detail={  # 抛出异常
                "status": "error",
                "error_code": "CLAUSE_NOT_FOUND",  # 字段
                "message": f"规范不存在: {clause_id}",  # 字段
            },
        )  # code

    adjustment = _learning_engine.compute_adjustment(clause_id, current)  # function call

    # 根据条件判断分支：if apply and adjustment.get("adjustable")
    if apply and adjustment.get("adjustable"):  # check: AND condition
        success = _learning_engine.apply_adjustment(  # assignment
            clause_id,
            adjustment["suggested_threshold"],
            _spec_repo,  # 操作
            reason=f"基于申诉 {feedback_id} 的自动微调",  # assignment
        )  # code
        adjustment["applied"] = success  # 操作

    return {"status": "success", "adjustment": adjustment}  # return: dict


# ── 审查结果对比（Diff） ─────────────────────────────────


@app.post("/review/compare")  # function call
async def review_compare(  # code
    file1: UploadFile = File(..., description="版本1（旧图纸）"),  # function call
    file2: UploadFile = File(..., description="版本2（新图纸）"),  # function call
    building_type: str = Query(
        "civil", description="建筑类型: civil(民用) / industrial(工业)"
    ),  # function call
    standard: str = Query(
        "GB 50016-2014", description="规范标准: GB 50016-2014 / NFPA 101-2021 / NFPA 5000-2021"
    ),  # function call
    api_key: str = Depends(verify_api_key),  # function call
):  # code
    """审查结果对比（Diff）

    上传同一图纸的两个版本，自动分别审查并对比差异：
    - 新增违规：新版新增的违规项
    - 消失违规：旧版有但新版已修复的违规项
    - 变化违规：同一实体值或状态发生变化

    返回结构化 Diff 报告，含变更摘要和逐条详情。
    """
    from src.baa_engine.review_diff import ReviewDiffEngine  # import

    loop = asyncio.get_event_loop()  # function call

    async def _run_review(file: UploadFile) -> tuple:  # function call
        content = await file.read()  # function call
        filename = file.filename or "unknown"  # assignment
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""  # function call

        if ext not in SUPPORTED_FORMATS:  # check: membership test
            raise HTTPException(
                status_code=400,
                detail={  # assignment
                    "status": "error",
                    "error_code": "UNSUPPORTED_FORMAT",  # code
                    "message": f"不支持的文件格式: {ext}",  # code
                },
            )  # code

        file_id = generate_file_id()  # function call
        file_path = store_file(content, file_id, ext)  # function call

        result = await loop.run_in_executor(  # assignment
            ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id  # function call
        )  # code
        if not result.success:  # check: negated condition
            raise HTTPException(
                status_code=400,
                detail={  # assignment
                    "status": "error",
                    "message": f"图纸解析失败: {result.error}",  # code
                },
            )  # code

        semantic = await loop.run_in_executor(  # assignment
            ENGINE_THREAD_POOL,  # code
            lambda: _semantic_analyzer.analyze(  # code
                result.primitives,
                result.dimensions,  # code
                building_type=building_type,
                dxf_path=str(file_path),  # function call
            ),  # code
        )  # code
        entities = semantic["entities"]  # assignment

        from src.baa_engine.spec_repository import SpecRepository  # import
        from collections import Counter  # stdlib: collections

        repo = SpecRepository()  # function call
        details = []  # assignment
        registry_funcs = _func_registry.list_all()  # check all true

        for e in entities:  # loop: iterate
            for func in registry_funcs:  # loop: iterate
                try:  # try block
                    threshold_val, unit, op = repo.get_threshold(  # assignment
                        func.clause_id, building_type, standard  # code
                    )  # code
                    func.threshold = threshold_val  # assignment
                    func.unit = unit  # assignment
                    func.operator = op  # assignment
                    r = _func_registry.execute_with_timeout(func, e)  # function call
                    if r is not None and r.result != "PASS":  # check: value is not None
                        clause = {  # assignment
                            "standard": standard,  # code
                            "clause_id": func.clause_id,  # code
                            "title": func.name,  # code
                            "text": func.description,  # code
                            "category": func.category.value,  # code
                        }  # code
                        f = _attribution_analyzer.build_finding(
                            r, clause, e, entities[:5]
                        )  # function call
                        details.append(
                            {  # code
                                "entity_id": e.get("id", ""),  # function call
                                "entity_type": e.get("type", ""),  # function call
                                "clause_id": f.clause.get("clause_id", ""),  # function call
                                "clause_title": f.clause.get("title", ""),  # function call
                                "result": f.judgement["result"],  # code
                                "extracted_value": r.actual,  # code
                                "required_value": threshold_val,  # code
                                "difference": (r.actual or 0) - threshold_val,  # function call
                                "explanation": f.explanation[:120],  # code
                            }
                        )  # code
                except Exception:  # catch exception
                    continue  # code

        # 缺失检查：对 EXIST-* 函数检查是否有匹配实体
        for func in registry_funcs:  # loop: iterate
            if func.category.value != "exist":  # check: OR condition
                continue  # code
            has_match = any(func.matches(e) for e in entities)  # check any true
            if not has_match:  # check: negated condition
                r = _func_registry.execute_with_timeout(func, None)  # function call
                if r is not None and r.result != "PASS":  # check: value is not None
                    clause = {  # assignment
                        "standard": standard,  # code
                        "clause_id": func.clause_id,  # code
                        "title": func.name,  # code
                        "text": func.description,  # code
                        "category": func.category.value,  # code
                    }  # code
                    f = _attribution_analyzer.build_finding(
                        r, clause, {}, entities[:5]
                    )  # function call
                    details.append(
                        {  # code
                            "entity_id": "",  # code
                            "entity_type": "missing",  # code
                            "clause_id": f.clause.get("clause_id", ""),  # function call
                            "clause_title": f.clause.get("title", ""),  # function call
                            "result": f.judgement["result"],  # code
                            "extracted_value": 0.0,  # code
                            "required_value": f.extracted_params.get(
                                "required_value", 1.0
                            ),  # function call
                            "difference": -f.extracted_params.get(
                                "required_value", 1.0
                            ),  # function call
                            "explanation": f.explanation[:120],  # code
                        }
                    )  # code

        return filename, details  # return

    name1, details1 = await _run_review(file1)  # function call
    name2, details2 = await _run_review(file2)  # function call

    engine = ReviewDiffEngine()  # function call
    report = engine.compare(  # assignment
        details1,
        details2,  # code
        v1_file=name1,  # assignment
        v2_file=name2,  # assignment
        v1_building_type=building_type,  # assignment
        v2_building_type=building_type,  # assignment
        v1_standard=standard,  # assignment
        v2_standard=standard,  # assignment
    )  # code

    return engine.to_json(report)  # return


# ── 启动入口 ──────────────────────────────────────────────

if __name__ == "__main__":  # condition: __name__ == "__main__":
    """直接运行本文件时启动 Uvicorn 服务器

    生产环境建议通过 Docker 或 systemd 管理进程生命周期。
    """
    import uvicorn  # import
    import sys  # import
    import os  # stdlib: filesystem ops

    port = int(os.getenv("BAA_PORT", "8000"))  # 服务端口
    workers = int(os.getenv("BAA_WORKERS", "4"))  # 默认4 worker

    # 日志输出到项目 data/logs/ 下
    log_dir = DATA_DIR / "logs"  # assignment
    log_dir.mkdir(parents=True, exist_ok=True)  # function call
    log_file = log_dir / "baa-api.log"  # assignment
    print(f"[BAA] 日志路径: {log_file}", flush=True)  # print output
    print(f"[BAA] Worker 数: {workers}", flush=True)  # print output

    uvicorn.run(  # code
        "src.api.baa_api:app",  # 应用模块路径
        host="0.0.0.0",  # assignment
        port=port,  # assignment
        workers=workers,  # assignment
        log_config=None,  # assignment
        access_log=False,  # assignment
        log_level="info",  # assignment
    )  # code
