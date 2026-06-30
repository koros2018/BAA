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
from typing import Optional, List  # 类型注解
from datetime import datetime, timedelta  # 日期时间处理

# ── FastAPI 及依赖 ──────────────────────────────────────────
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Security, Query, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


# ═══════════════════════════════════════════════════════════════
# 配置区
# ═══════════════════════════════════════════════════════════════

# ── 项目工作路径（默认：项目根目录下的 data/） ───────────

# 计算项目根目录（src/../）并加入 sys.path，确保模块可导入
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # src/../
import sys
if str(PROJECT_ROOT) not in sys.path:  # 条件判断
    sys.path.insert(0, str(PROJECT_ROOT))  # 调用

# 数据目录：优先使用环境变量 BAA_DATA_DIR，否则默认为 data/
DATA_DIR = Path(os.getenv("BAA_DATA_DIR", str(PROJECT_ROOT / "data")))  # 赋值
FILES_DIR = DATA_DIR / "files"       # 上传的图纸文件存储目录
MODELS_DIR = DATA_DIR / "models"     # YOLO 模型文件目录
DATA_DIR.mkdir(parents=True, exist_ok=True)  # 赋值
FILES_DIR.mkdir(parents=True, exist_ok=True)  # 赋值
MODELS_DIR.mkdir(parents=True, exist_ok=True)  # 赋值

# ── 异步任务存储（内存） ───────────────────────────────────
from collections import Counter

# EMA2 第三方对接用：异步审查任务 + Webhook 回调的全局存储
_tasks = {}     # task_id -> {status, result, created_at, webhook_url, ...}
_webhooks = {}  # webhook_id -> {url, events, active, ...}

# 支持的文件格式（DWG/DXF）
SUPPORTED_FORMATS = {"dxf", "dwg"}  # 赋值
MAX_FILE_SIZE_MB = 50  # 赋值
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024  # 上传文件大小上限（50MB）

# ── API 密钥（从环境变量加载） ────────────────────────────
API_KEYS = set()  # 赋值
_api_key = os.getenv("BAA_API_KEY", "")  # 赋值
if _api_key:  # 条件判断
    API_KEYS.add(_api_key)  # 调用

# ── 共享密钥（用于 auth_token 验证，支持多密钥宽限期） ──
# 格式：逗号分隔，第一个为最新密钥，后续为旧密钥（48h宽限期）
AUTH_SECRETS = [s.strip() for s in os.getenv("BAA_AUTH_SECRET", "").split(",") if s.strip()]  # 赋值
if not AUTH_SECRETS:  # 条件判断
    # 开发模式默认密钥（生产环境必须通过环境变量设置）
    AUTH_SECRETS = ["baa-dev-secret-change-in-production"]  # 赋值


# ── 线程池（CPU密集型引擎任务用） ─────────────────────────
import asyncio
from concurrent.futures import ThreadPoolExecutor

# 引擎线程池：用于在独立线程中执行 CPU 密集的图纸分析任务
# 避免阻塞 FastAPI 的异步事件循环
ENGINE_THREAD_POOL = ThreadPoolExecutor(  # 赋值
    max_workers=min(8, (os.cpu_count() or 4) * 2),  # 赋值
    thread_name_prefix="baa-engine"  # 赋值
)  # 闭合


# ── 授权验证 ──────────────────────────────────────────────

# HMAC-SHA256 签名与 Base64 编解码（用于 auth_token 的 JWT 式实现）
import hmac
import hashlib
import base64


# ── API密钥管理 ──────────────────────────────────────────

# 密钥管理器：支持 API Key 的创建、轮换、撤销、权限验证
from src.baa_engine.api_key_manager import get_key_manager, ApiKeyPermission
# 反馈引擎：用户违规申诉 → 模型微调的学习闭环
from src.baa_engine.feedback_engine import FeedbackManager, LearningEngine


def generate_auth_token(payload: dict, secret: str = None) -> str:
    """生成 auth_token（JWT格式，HMAC-SHA256）
    默认使用最新密钥
    """
    if secret is None:  # 条件判断
        secret = AUTH_SECRETS[0]  # 使用最新密钥
    # ── 构造 JWT Header（算法 + 类型） ──────────────────────
    header = {"alg": "HS256", "typ": "JWT"}  # 赋值
    header_b64 = base64.urlsafe_b64encode(  # 赋值
        json.dumps(header, separators=(",", ":")).encode()).rstrip(b"=").decode()  # 调用
    # ── Base64 编码 Payload ─────────────────────────────────
    payload_b64 = base64.urlsafe_b64encode(  # 赋值
        json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=").decode()  # 调用
    # ── HMAC-SHA256 签名 ────────────────────────────────────
    signing_input = f"{header_b64}.{payload_b64}"  # 赋值
    sig = hmac.new(  # 赋值
        secret.encode(), signing_input.encode(), hashlib.sha256  # 调用
    ).digest()  # 闭合
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()  # 赋值
    return f"{header_b64}.{payload_b64}.{sig_b64}"  # 返回


def verify_auth_token(token: str) -> Optional[dict]:
    """验证 auth_token，使用所有活跃密钥（支持密钥宽限期）
    
    遍历 AUTH_SECRETS 列表，依次尝试用每个密钥验证签名。
    旧密钥在 48h 宽限期内仍有效，确保密钥轮换期间不影响已有 token。
    """
    for secret in AUTH_SECRETS:  # 循环
        result = _verify_with_secret(token, secret)  # 赋值
        if result is not None:  # 条件判断
            return result  # 返回
    return None  # 返回


def _verify_with_secret(token: str, secret: str) -> Optional[dict]:
    """用单个密钥验证 token
    
    Args:
        token: 待验证的 JWT 格式 token
        secret: HMAC 签名密钥
    
    Returns:
        验证通过返回 payload 字典，失败返回 None
    """
    try:  # 尝试
        # ── 解析 JWT 三段式结构 ──────────────────────────────
        parts = token.split(".")  # 赋值
        if len(parts) != 3:  # 条件判断
            return None  # 返回

        header_b64, payload_b64, sig_b64 = parts  # 赋值
        signing_input = f"{header_b64}.{payload_b64}"  # 赋值

        def add_padding(s):
            """Base64 URL-safe 解码需要补齐 '=' 填充符"""
            return s + "=" * (4 - len(s) % 4)  # 返回

        # ── 重新计算签名并与 token 中的签名比较 ──────────────
        expected_sig = hmac.new(  # 赋值
            secret.encode(), signing_input.encode(), hashlib.sha256  # 调用
        ).digest()  # 闭合

        actual_sig = base64.urlsafe_b64decode(add_padding(sig_b64))  # 赋值
        if not hmac.compare_digest(expected_sig, actual_sig):  # 条件判断
            return None  # 返回

        # ── 解码 payload ─────────────────────────────────────
        payload = json.loads(base64.urlsafe_b64decode(add_padding(payload_b64)))  # 赋值

        # ── 验证有效期（兼容带时区和不带时区的时间字符串） ──
        expires = payload.get("expires_at")  # 赋值
        if expires:  # 条件判断
            from datetime import timezone
            exp_time = datetime.fromisoformat(expires)  # 赋值
            if exp_time.tzinfo is None:  # 条件判断
                exp_time = exp_time.replace(tzinfo=timezone.utc)  # 赋值
            if datetime.now(timezone.utc) > exp_time:  # 条件判断
                return None  # token 已过期

        return payload  # 返回
    except Exception:  # 捕获异常
        return None  # 返回


# ── FastAPI 应用 ──────────────────────────────────────────

# 前端静态文件路径
FRONTEND_DIR = PROJECT_ROOT / "src" / "frontend"  # 赋值


# ── 引擎预热（app启动时加载） ──────────────────────────────

def _load_engine():
    """预热加载引擎模块，每个 worker 启动时执行一次"""
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.semantic_analyzer import SemanticAnalyzer
    from src.baa_engine.atomic_functions import FuncRegistry
    from src.baa_engine.attribution_analyzer import AttributionAnalyzer
    from src.baa_engine.spec_repository import SpecRepository
    global _drawing_parser, _semantic_analyzer, _func_registry, _attribution_analyzer, _spec_repo, _feedback_manager, _learning_engine  # 全局变量
    _drawing_parser = DrawingParser()  # 赋值
    _semantic_analyzer = SemanticAnalyzer()  # 赋值
    _func_registry = FuncRegistry()  # 赋值
    _attribution_analyzer = AttributionAnalyzer()  # 赋值
    _spec_repo = SpecRepository()  # 赋值
    _feedback_manager = FeedbackManager(DATA_DIR)  # 赋值
    _learning_engine = LearningEngine(_feedback_manager)  # 赋值
    print(f"[BAA] 引擎已预热: {_func_registry.count}个原子函数, {_spec_repo.count}条规范")  # 调用
    print(f"[BAA] 反馈闭环已加载: {_feedback_manager.stats()['total']}条申诉")  # 调用


from contextlib import asynccontextmanager


import gc

# ── 内存监控（每 300 秒触发 GC，防止内存泄漏） ─────────
_GC_INTERVAL = 300  # 秒
_last_gc_time = 0  # 上次 GC 时间戳


def _periodic_gc():
    """定时 GC 回收，防止大图纸解析后的内存堆积"""
    global _last_gc_time
    now = time.time()
    if now - _last_gc_time > _GC_INTERVAL:
        gc.collect()
        _last_gc_time = now


# ── 并发限制（防止大图纸爆炸） ──────────────────────────
MAX_CONCURRENT_REVIEWS = 4  # 最大并发审查数
_review_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REVIEWS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理
    
    启动时：在线程池中异步预热引擎各模块，避免阻塞事件循环
    关闭时：优雅关闭线程池
    """
    # 启动时：预热引擎
    loop = asyncio.get_event_loop()  # 赋值
    await loop.run_in_executor(ENGINE_THREAD_POOL, _load_engine)  # 操作
    yield  # 生成
    # 关闭时：清理线程池
    ENGINE_THREAD_POOL.shutdown(wait=False)  # 赋值


app = FastAPI(title="BAA API", version="1.0.0", lifespan=lifespan)  # 赋值
security = HTTPBearer(auto_error=False)  # 赋值

# ── 挂载前端静态文件 ──────────────────────────────────────
if FRONTEND_DIR.exists():  # 条件判断
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")  # 调用


@app.get("/")
async def root():
    """返回前端 UI 页面
    
    优先返回静态 HTML 页面（前端 SPA）；
    如果前端文件不存在，降级返回 JSON 格式的 API 信息。
    """
    from fastapi.responses import HTMLResponse
    index_path = FRONTEND_DIR / "index.html"  # 赋值
    if index_path.exists():  # 条件判断
        content = index_path.read_text(encoding="utf-8")  # 赋值
        return HTMLResponse(content=content, status_code=200)  # 返回
    # 降级：返回 JSON 信息（前端文件未部署时使用）
    return {  # 返回
        "service": "BAA - Building Audit Assistant",  # 字段
        "version": "1.0.0",  # 字段
        "api_docs": "/docs",  # 字段
        "endpoints": {  # 字段
            "/health": "服务健康检查",  # 字段
            "/deconstruct": "图纸解析与违规范判定",  # 字段
            "/review": "图纸合规审查（详细报告）",  # 字段
            "/reconstruct": "图纸重构",  # 字段
            "/order/{order_id}": "查询订单/任务状态",  # 字段
        },  # 闭合
        "note": "前端 UI 文件未找到，请检查 src/frontend/index.html"  # 字段
    }  # 闭合

# ── CORS 中间件（允许跨域访问） ────────────────────────────
app.add_middleware(  # 调用
    CORSMiddleware,  # 解包
    allow_origins=["*"],        # 允许所有来源（开发阶段）
    allow_credentials=True,  # 赋值
    allow_methods=["*"],  # 赋值
    allow_headers=["*"],  # 赋值
)  # 闭合


def get_api_key(authorization: str = Query("", description="Bearer API Key")):
    """从 Query 参数中获取 API Key（兼容 Swagger UI 调试）"""
def verify_api_key(request: Request):
    """验证 API Key（使用 ApiKeyManager）
    
    验证流程：
    1. 如果未配置 API_KEYS（开发模式），跳过验证，返回 anonymous
    2. 从 Authorization Header 提取 Bearer token
    3. 使用 ApiKeyManager 验证密钥是否有效
    4. 如果是环境变量中的密钥也放行
    5. 开发模式下无效密钥也放行（anonymous）
    """
    if not API_KEYS:  # 条件判断
        return "anonymous"  # 返回
    auth_header = request.headers.get("authorization", "")  # 赋值
    
    if auth_header.startswith("Bearer "):  # 条件判断
        token = auth_header[7:]  # 赋值
    else:  # 否则
        return "anonymous"  # 开发模式：没传key也放行
    
    # 使用 ApiKeyManager 验证（数据库中的密钥）
    km = get_key_manager()  # 赋值
    key_info = km.validate_key(token)  # 赋值
    if key_info:  # 条件判断
        km.record_usage(token)  # 调用
        return token  # 返回
    
    # 环境变量密钥也放行
    if token in API_KEYS:  # 条件判断
        return token  # 返回
    
    # 开发模式：没传有效key也放行
    return "anonymous"  # 返回


def require_admin(request: Request, api_key: str = ""):
    """验证 admin 权限（用于 admin 端点）
    
    验证逻辑：
    1. 开发模式（API_KEYS 为空）时不校验，直接放行
    2. 使用 ApiKeyManager 验证密钥是否具有 admin 权限
    3. 环境变量中的密钥也视为 admin 权限
    """
    if not API_KEYS:  # 条件判断
        return "anonymous"  # 返回
    km = get_key_manager()  # 赋值
    key_info = km.validate_key(api_key)  # 赋值
    if key_info and key_info.get("permission") == "admin":  # 条件判断
        return api_key  # 返回
    # 环境变量key也视为admin
    if api_key and api_key in API_KEYS:  # 条件判断
        return api_key  # 返回
    raise HTTPException(status_code=403, detail={  # 抛出异常
        "status": "error", "error_code": "FORBIDDEN",  # 字段
        "message": "需要admin权限"  # 字段
    })  # 闭合


# ── 文件管理 ──────────────────────────────────────────────

def generate_file_id() -> str:
    """生成唯一文件标识符（UUID 前 12 位）"""
    return f"baa-file-{uuid.uuid4().hex[:12]}"  # 返回


def store_file(content: bytes, file_id: str, extension: str) -> Path:
    """将上传文件保存到磁盘
    
    Args:
        content: 文件二进制内容
        file_id: 文件唯一标识符
        extension: 文件扩展名（dwg/dxf）
    
    Returns:
        保存后的文件路径
    """
    path = FILES_DIR / f"{file_id}.{extension}"  # 赋值
    path.write_bytes(content)  # 调用
    return path  # 返回


def get_file_path(file_id: str) -> Optional[Path]:
    """根据文件 ID 查找已存储的图纸文件
    
    遍历所有支持的文件格式，找到匹配的文件。
    
    Args:
        file_id: 文件唯一标识符
    
    Returns:
        文件路径（如果存在），否则 None
    """
    for ext in SUPPORTED_FORMATS:  # 循环
        path = FILES_DIR / f"{file_id}.{ext}"  # 赋值
        if path.exists():  # 条件判断
            return path  # 返回
    return None  # 返回


# ── 引擎导入（懒加载） ──────────────────────────────────

# ── 引擎引用（由 lifespan 预热加载） ──────────────────────

# 各引擎模块的全局引用，在 app 启动时通过 _load_engine() 初始化
_drawing_parser = None         # 图纸解析器
_semantic_analyzer = None       # 语义分析器
_func_registry = None           # 原子函数注册表
_attribution_analyzer = None    # 属性推断引擎
_spec_repo = None               # 规范知识库

# ── 反馈闭环引擎（P10） ────────────────────────────────────
_feedback_manager: Optional[FeedbackManager] = None  # 赋值
_learning_engine: Optional[LearningEngine] = None  # 操作


@app.get("/health")
async def health():
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
    engine_ok = _func_registry is not None  # 赋值
    spec_ok = _spec_repo is not None  # 赋值
    parser_ok = _drawing_parser is not None  # 赋值
    yolo_ok = False  # 赋值
    yolo_info = "未加载"  # 赋值
    try:  # 尝试
        from src.baa_engine.yolo_integrator import get_yolo_model
        yolo_model = get_yolo_model()  # 赋值
        if yolo_model is not None:  # 条件判断
            yolo_ok = True  # 赋值
            yolo_info = "就绪"  # 赋值
    except Exception:  # 捕获异常
        yolo_info = "不可用"  # 赋值
    
    import psutil
    process = psutil.Process()
    mem_info = process.memory_info()

    all_ok = engine_ok and spec_ok and parser_ok  # 赋值
    return {  # 返回
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
            "yolo_integrator": {"status": "ok" if yolo_ok else "unavailable", "info": yolo_info},  # 字段
        },  # 闭合
        "data_dir": str(DATA_DIR),  # 字段
        "memory": {  # 字段
            "rss_mb": round(mem_info.rss / 1024 / 1024, 1),  # 字段
            "vms_mb": round(mem_info.vms / 1024 / 1024, 1),  # 字段
        },  # 闭合
    }  # 闭合

# ── 记录服务启动时间 ───────────────────────────────────────
_start_time = time.time()  # 赋值


@app.post("/deconstruct")
async def deconstruct(
    file: UploadFile = File(...),  # 赋值
    building_type: str = Query("civil", description="建筑类型: civil(民用) / industrial(工业)"),  # 赋值
    use_yolo: bool = Query(False, description="是否使用 YOLO 图元检测增强"),  # 赋值
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
):  # 闭合
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
    filename = file.filename or "unknown"  # 赋值
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""  # 赋值

    if ext not in SUPPORTED_FORMATS:  # 条件判断
        raise HTTPException(  # 抛出异常
            status_code=400,  # 赋值
            detail={  # 赋值
                "status": "error",  # 字段
                "error_code": "UNSUPPORTED_FORMAT",  # 字段
                "message": f"不支持的文件格式: {ext}。支持: {', '.join(SUPPORTED_FORMATS)}",  # 字段
            }  # 闭合
        )  # 闭合

    # ── 检查文件大小 ────────────────────────────────────────
    content = await file.read()  # 赋值
    if len(content) > MAX_FILE_SIZE:  # 条件判断
        raise HTTPException(  # 抛出异常
            status_code=400,  # 赋值
            detail={  # 赋值
                "status": "error",  # 字段
                "error_code": "FILE_TOO_LARGE",  # 字段
                "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",  # 字段
            }  # 闭合
        )  # 闭合

    # ── 存储文件到磁盘 ──────────────────────────────────────
    file_id = generate_file_id()  # 赋值
    file_path = store_file(content, file_id, ext)  # 赋值

    # ── 调用核心引擎进行解析 ─────────────────────────────────
    start = time.time()  # 赋值
    loop = asyncio.get_event_loop()  # 赋值

    # Step 1: 图纸解析（CPU密集型 → 线程池）
    # 将 DWG/DXF 文件解析为基本图元（线、弧、圆、文字等）
    result = await loop.run_in_executor(  # 赋值
        ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id  # 操作
    )  # 闭合
    if not result.success:  # 条件判断
        return {  # 返回
            "status": "error",  # 字段
            "error_code": "PARSE_FAILED",  # 字段
            "message": f"图纸解析失败: {result.error}",  # 字段
            "file_id": file_id,  # 字段
        }  # 闭合

    # Step 2: 语义分析（CPU密集型 → 线程池）
    # 识别墙、门、窗、楼梯、防火分区等语义实体
    semantic = await loop.run_in_executor(  # 赋值
        ENGINE_THREAD_POOL,  # 解包
        lambda: _semantic_analyzer.analyze(  # 操作
            result.primitives, result.dimensions,  # 解包
            building_type=building_type  # 赋值
        )  # 闭合
    )  # 闭合
    entities = semantic["entities"]  # 赋值
    relations = semantic["relations"]  # 赋值

    # Step 2.5: YOLO 图元检测增强（可选）
    # 使用 CV 模型辅助识别规则解析遗漏的实体
    if use_yolo:  # 条件判断
        try:  # 尝试
            from src.baa_engine.yolo_integrator import YOLODetectionIntegrator
            yolo = YOLODetectionIntegrator()  # 赋值
            if yolo.load_model():  # 条件判断
                _, dets = yolo.render_and_predict(str(file_path))  # 赋值
                yolo_entities = yolo.detections_to_entities(dets)  # 赋值
                # 合并到实体列表（去重，优先保留规则解析结果）
                existing_types = set(e.get("type", "") for e in entities)  # 赋值
                for ye in yolo_entities:  # 循环
                    if ye["type"] not in existing_types:  # 条件判断
                        entities.append(ye)  # 调用
        except Exception as yolo_e:  # 捕获异常
            # YOLO 失败不影响主流程
            pass  # 占位

    # Step 2.75: DIMENSION 尺寸标注注入（自动反推实体属性）
    try:  # 尝试
        from src.baa_engine.dimension_parser import DimensionParser
        dp = DimensionParser()  # 赋值
        dims = dp.extract_dimensions(str(file_path))  # 赋值
        if dims:  # 条件判断
            entities = dp.inject_into_entities(dims, entities)  # 赋值
    except Exception:  # 捕获异常
        pass  # 占位

    # Step 3: 规范判定（使用 building_type 确定阈值，含去重）
    # 遍历所有实体和所有原子函数，逐项检查合规性
    from src.baa_engine.spec_repository import SpecRepository
    repo = SpecRepository()  # 赋值
    findings = []  # 赋值
    registry_funcs = _func_registry.list_all()  # 赋值
    total_checks = 0  # 赋值
    seen_violations = set()  # (clause_id, entity_type) 用于 FAIL 去重

    for e in entities:  # 循环
        for func in registry_funcs:  # 循环
            total_checks += 1  # 赋值
            # 根据建筑类型获取阈值参数
            threshold_val, unit, op = repo.get_threshold(func.clause_id, building_type)  # 赋值
            func.threshold = threshold_val  # 赋值
            func.unit = unit  # 赋值
            func.operator = op  # 赋值
            r = func.execute(e)  # 赋值
            if r is not None and r.result != "PASS":  # 条件判断
                # 去重：同一 clause_id + 同一 entity_type 只记一次 FAIL
                etype = e.get("type", "")  # 赋值
                dedup_key = (func.clause_id, etype)  # 赋值
                is_dup = dedup_key in seen_violations  # 赋值
                if r.result == "FAIL":  # 条件判断
                    seen_violations.add(dedup_key)  # 调用
                
                clause = {  # 赋值
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # 闭合
                f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])  # 赋值
                # 详细的违规信息输出
                finding_detail = {  # 赋值
                    "finding_id": f.finding_id,  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "clause_title": func.name,  # 字段
                    "description": func.description,  # 字段
                    "entity_type": etype,  # 字段
                    "result": r.result,  # 字段
                    "severity": getattr(r, 'severity', 'major'),  # 字段
                    "extracted_value": getattr(r, 'extracted_value', getattr(r, 'value', 0)),  # 字段
                    "required_value": threshold_val,  # 字段
                    "explanation": getattr(f, 'explanation', f.description[:100] if hasattr(f, 'description') else ''),  # 字段
                    "is_duplicate": is_dup,  # 字段
                }  # 闭合
                findings.append(finding_detail)  # 调用

    # 缺失检查：对 EXIST-* 函数检查是否有匹配实体
    # 例如"应有防火门"→检查是否存在 fire_door 实体
    for func in registry_funcs:  # 循环
        if func.category.value != "exist":  # 条件判断
            continue  # 继续循环
        has_match = any(func.matches(e) for e in entities)  # 赋值
        if not has_match:  # 条件判断
            total_checks += 1  # 赋值
            r = func.execute(None)  # 赋值
            if r is not None and r.result != "PASS":  # 条件判断
                dedup_key = (func.clause_id, "missing")  # 赋值
                is_dup = dedup_key in seen_violations  # 赋值
                if r.result == "FAIL":  # 条件判断
                    seen_violations.add(dedup_key)  # 调用
                
                clause = {  # 赋值
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # 闭合
                f = _attribution_analyzer.build_finding(r, clause, {}, entities[:5])  # 赋值
                finding_detail = {  # 赋值
                    "finding_id": f.finding_id,  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "clause_title": func.name,  # 字段
                    "description": func.description,  # 字段
                    "entity_type": "missing",  # 字段
                    "result": r.result,  # 字段
                    "severity": 'critical',  # 字段
                    "extracted_value": 0,  # 字段
                    "required_value": 1,  # 字段
                    "explanation": f"缺少{func.name}相关实体（{func.description}）",  # 字段
                    "is_duplicate": is_dup,  # 字段
                }  # 闭合
                findings.append(finding_detail)  # 调用

    # 统计
    type_stats = {}  # 赋值
    for e in entities:  # 循环
        t = e["type"]  # 赋值
        if t not in type_stats:  # 条件判断
            type_stats[t] = {"count": 0, "bbox_areas": []}  # 操作
        type_stats[t]["count"] += 1  # 操作
        bbox = e["bbox"]  # 赋值
        type_stats[t]["bbox_areas"].append(bbox.get("width", 0) * bbox.get("height", 0))  # 操作

    elements = []  # 赋值
    for t, stats in sorted(type_stats.items()):  # 循环
        areas = stats["bbox_areas"]  # 赋值
        total_area = sum(areas) if areas else 0  # 赋值
        elem = {"type": t, "count": stats["count"]}  # 赋值
        if t in ("wall", "corridor", "stair"):  # 条件判断
            elem["total_length_m"] = round(total_area ** 0.5, 1)  # 操作
        elif t in ("door", "fire_door", "window"):  # 分支
            elem["total_count"] = stats["count"]  # 操作
        elif t == "fire_zone":  # 分支
            elem["total_area_sqm"] = round(total_area, 1)  # 操作
        elements.append(elem)  # 调用

    elapsed = int((time.time() - start) * 1000)  # 赋值

    # ── 统计违规严重度分布（去重后） ────────────────────────
    fail_count = len([f for f in findings if f["result"] == "FAIL" and not f["is_duplicate"]])  # 赋值
    warn_count = len([f for f in findings if f["result"] == "WARN" and not f["is_duplicate"]])  # 赋值
    critical_count = len([f for f in findings if f.get("severity") == "critical" and not f["is_duplicate"]])  # 赋值

    result = {  # 赋值
        "status": "success",  # 字段
        "elements": elements,              # 实体类型统计
        "relations": len(relations),       # 实体间关系数量
        "findings": findings,              # 完整违规详情（含去重标记）
        "total_checks": total_checks,      # 总检查项数
        "summary": {  # 字段
            "total_violations": fail_count,  # 字段
            "warnings": warn_count,  # 字段
            "critical": critical_count,  # 字段
            "total_checks": total_checks,  # 字段
        },  # 闭合
        "confidence": 0.85 if len(entities) > 0 else 0,  # 解析置信度
        "file_id": file_id,  # 字段
        "building_type": building_type,  # 字段
        "processing_time_ms": elapsed,  # 字段
    }  # 闭合

    if use_yolo:  # 条件判断
        result["yolo_entities"] = len(yolo_entities)  # 操作
        result["yolo_enabled"] = True  # 操作

    return result  # 返回


@app.post("/review")
async def review(
    file: UploadFile = File(...),  # 赋值
    full: bool = Query(False, description="返回完整图元列表"),  # 赋值
    building_type: str = Query("civil", description="建筑类型: civil(民用) / industrial(工业)"),  # 赋值
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
):  # 闭合
    """图纸合规审查（免费试用）

    对上传的 DWG/DXF 图纸进行完整合规审查，返回：
    - 审查摘要（实体统计、检查项数、违规分布）
    - 违规详情（每条违规的 clause_id、提取值、要求值、差值）
    - 修正建议（基于 correction_engine 生成）

    与 /deconstruct 的区别：
    - /deconstruct 侧重"拆解"，输出结构化实体数据
    - /review 侧重"审查"，输出合规报告和修正建议
    """
    # ── 检查文件格式 ────────────────────────────────────────
    filename = file.filename or "unknown"  # 赋值
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""  # 赋值

    if ext not in SUPPORTED_FORMATS:  # 条件判断
        raise HTTPException(  # 抛出异常
            status_code=400,  # 赋值
            detail={  # 赋值
                "status": "error",  # 字段
                "error_code": "UNSUPPORTED_FORMAT",  # 字段
                "message": f"不支持的文件格式: {ext}",  # 字段
            }  # 闭合
        )  # 闭合

    # ── 检查文件大小 ────────────────────────────────────────
    content = await file.read()  # 赋值
    if len(content) > MAX_FILE_SIZE:  # 条件判断
        raise HTTPException(  # 抛出异常
            status_code=400,  # 赋值
            detail={  # 赋值
                "status": "error",  # 字段
                "error_code": "FILE_TOO_LARGE",  # 字段
                "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",  # 字段
            }  # 闭合
        )  # 闭合

    # ── 存储文件到磁盘 ──────────────────────────────────────
    file_id = generate_file_id()  # 赋值
    file_path = store_file(content, file_id, ext)  # 赋值

    start = time.time()  # 赋值
    loop = asyncio.get_event_loop()  # 赋值

    # Step 1: 图纸解析（CPU密集型 → 线程池）
    result = await loop.run_in_executor(  # 赋值
        ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id  # 操作
    )  # 闭合
    if not result.success:  # 条件判断
        return {  # 返回
            "status": "error",  # 字段
            "error_code": "PARSE_FAILED",  # 字段
            "message": f"图纸解析失败: {result.error}",  # 字段
            "file_id": file_id,  # 字段
        }  # 闭合

    # Step 2: 语义分析（CPU密集型 → 线程池）
    semantic = await loop.run_in_executor(  # 赋值
        ENGINE_THREAD_POOL,  # 解包
        lambda: _semantic_analyzer.analyze(  # 操作
            result.primitives, result.dimensions,  # 解包
            building_type=building_type  # 赋值
        )  # 闭合
    )  # 闭合
    entities = semantic["entities"]  # 赋值

    # Step 3: 规范判定（使用 building_type 确定阈值）
    from src.baa_engine.spec_repository import SpecRepository
    repo = SpecRepository()  # 赋值
    from collections import Counter
    clause_results = Counter()  # 赋值
    details = []  # 赋值
    registry_funcs = _func_registry.list_all()  # 赋值

    # 收集已出现的实体类型
    found_entity_types = set(e["type"] for e in entities)  # 赋值

    for e in entities:  # 循环
        for func in registry_funcs:  # 循环
            # 根据 building_type 获取实际阈值
            threshold_val, unit, op = repo.get_threshold(func.clause_id, building_type)  # 赋值
            func.threshold = threshold_val  # 赋值
            func.unit = unit  # 赋值
            func.operator = op  # 赋值
            r = func.execute(e)  # 赋值
            if r is None:  # 条件判断
                continue  # 继续循环
            clause_results[func.clause_id] += 1  # 赋值
            if r.result != "PASS":  # 条件判断
                clause = {  # 赋值
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # 闭合
                f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])  # 赋值
                details.append({  # 调用
                    "entity_id": e.get("id", e.get("type", "")),  # 字段
                    "entity_type": e["type"],  # 字段
                    "clause_id": f.clause.get("clause_id", ""),  # 字段
                    "clause_title": f.clause.get("title", ""),  # 字段
                    "result": f.judgement["result"],  # 字段
                    "extracted_value": f.extracted_params["extracted_value"],  # 字段
                    "required_value": f.extracted_params.get("required_value", 1.2),  # 字段
                    "difference": f.extracted_params.get("difference", 0),  # 字段
                    "explanation": f.explanation[:120],  # 字段
                })  # 闭合

    # 缺失检查：对 EXIST-* 函数检查是否有匹配实体
    for func in registry_funcs:  # 循环
        if func.category.value != "exist":  # 条件判断
            continue  # 继续循环
        has_match = any(func.matches(e) for e in entities)  # 赋值
        if not has_match:  # 条件判断
            r = func.execute(None)  # 触发缺失检查模式
            if r is not None and r.result != "PASS":  # 条件判断
                clause = {  # 赋值
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # 闭合
                f = _attribution_analyzer.build_finding(r, clause, {}, entities[:5])  # 赋值
                details.append({  # 调用
                    "entity_id": "",  # 字段
                    "entity_type": "missing",  # 字段
                    "clause_id": f.clause.get("clause_id", ""),  # 字段
                    "clause_title": f.clause.get("title", ""),  # 字段
                    "result": f.judgement["result"],  # 字段
                    "extracted_value": 0.0,  # 字段
                    "required_value": f.extracted_params.get("required_value", 1.0),  # 字段
                    "difference": -f.extracted_params.get("required_value", 1.0),  # 字段
                    "explanation": f.explanation[:120],  # 字段
                })  # 闭合

    elapsed = int((time.time() - start) * 1000)  # 赋值

    # ── 统计 ─────────────────────────────────────────────────
    entity_types = Counter(e["type"] for e in entities)        # 各类型实体数量
    violation_count = Counter(d["clause_id"] for d in details)  # 各规范条款违规数

    response_data = {  # 赋值
        "status": "success",  # 字段
        "summary": {  # 字段
            "total_entities": len(entities),  # 字段
            "entity_types": dict(entity_types),  # 字段
            "total_checks": len(entities) * len(registry_funcs),  # 字段
            "violations": len(details),  # 字段
            "violation_by_clause": dict(violation_count.most_common(10)),  # 字段
        },  # 闭合
        "details": details[:100],  # 最多返回100条详情
        "file_id": file_id,  # 字段
        "building_type": building_type,  # 字段
        "processing_time_ms": elapsed,  # 字段
    }  # 闭合

    # ── 生成修正建议（基于 CorrectionEngine） ────────────────
    try:  # 尝试
        from src.baa_engine.correction_engine import CorrectionEngine
        correction_engine = CorrectionEngine()  # 赋值
        review_result_for_correction = {  # 赋值
            "findings": [{  # 字段
                "entity_id": d["entity_id"],  # 字段
                "entity_type": d["entity_type"],  # 字段
                "clause_id": d["clause_id"],  # 字段
                "clause_title": d["clause_title"],  # 字段
                "extracted_value": d["extracted_value"],  # 字段
                "required_value": d["required_value"],  # 字段
                "difference": d["difference"],  # 字段
            } for d in details]  # 闭合
        }  # 闭合
        corrections = correction_engine.generate_for_result(review_result_for_correction)  # 赋值
        response_data["corrections"] = corrections  # 操作
    except Exception as e:  # 捕获异常
        response_data["corrections"] = []  # 操作

    # ── 如果请求 full 模式，返回完整图元列表 ─────────────────
    if full:  # 条件判断
        response_data["all_entities"] = [  # 操作
            {"id": e.get("id", e.get("type", "")), "type": e["type"], "bbox": e["bbox"]}  # 字面量
            for e in entities  # 循环
        ]  # 闭合

    return response_data  # 返回


@app.post("/batch-review")
async def batch_review(
    files: List[UploadFile] = File(...),  # 操作
    building_type: str = Query("civil", description="建筑类型: civil(民用) / industrial(工业)"),  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
):  # 闭合
    """多文件批量审查

    同时审查最多 20 个图纸文件，返回每个文件的单独审查结果，
    以及跨文件的交叉分析（同一违规类别在多少文件中出现）。
    """
    if len(files) < 1:  # 条件判断
        raise HTTPException(status_code=400, detail={"status": "error", "message": "请至少上传一个文件"})  # 抛出异常
    if len(files) > 20:  # 条件判断
        raise HTTPException(status_code=400, detail={"status": "error", "message": "单次最多审查20个文件"})  # 抛出异常

    start = time.time()  # 赋值
    loop = asyncio.get_event_loop()  # 赋值
    from src.baa_engine.spec_repository import SpecRepository
    from collections import Counter
    repo = SpecRepository()  # 赋值
    registry_funcs = _func_registry.list_all()  # 赋值

    results = []  # 赋值
    all_details = []  # 赋值
    all_entities = []  # 赋值
    total_violations = 0  # 赋值
    total_checks = 0  # 赋值

    # ── 遍历每个文件，逐一审查 ──────────────────────────────
    for file in files:  # 循环
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""  # 赋值
        if ext not in SUPPORTED_FORMATS:  # 条件判断
            results.append({  # 调用
                "filename": file.filename,  # 字段
                "status": "error",  # 字段
                "error_code": "UNSUPPORTED_FORMAT",  # 字段
                "message": f"不支持的文件格式: {ext}",  # 字段
            })  # 闭合
            continue  # 继续循环

        content = await file.read()  # 赋值
        if len(content) > MAX_FILE_SIZE:  # 条件判断
            results.append({  # 调用
                "filename": file.filename,  # 字段
                "status": "error",  # 字段
                "error_code": "FILE_TOO_LARGE",  # 字段
                "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",  # 字段
            })  # 闭合
            continue  # 继续循环

        file_id = generate_file_id()  # 赋值
        file_path = store_file(content, file_id, ext)  # 赋值

        # ── 解析（CPU密集型 → 线程池） ───────────────────────
        result = await loop.run_in_executor(  # 赋值
            ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id  # 操作
        )  # 闭合
        if not result.success:  # 条件判断
            results.append({  # 调用
                "filename": file.filename,  # 字段
                "status": "error",  # 字段
                "error_code": "PARSE_FAILED",  # 字段
                "message": f"图纸解析失败: {result.error}",  # 字段
            })  # 闭合
            continue  # 继续循环

        # ── 语义分析（CPU密集型 → 线程池） ───────────────────
        semantic = await loop.run_in_executor(  # 赋值
            ENGINE_THREAD_POOL,  # 解包
            lambda: _semantic_analyzer.analyze(  # 操作
                result.primitives, result.dimensions,  # 解包
                building_type=building_type  # 赋值
            )  # 闭合
        )  # 闭合
        entities = semantic["entities"]  # 赋值

        # ── 规范判定 ──────────────────────────────────────────
        details = []  # 赋值
        found_entity_types = set(e["type"] for e in entities)  # 赋值

        for e in entities:  # 循环
            for func in registry_funcs:  # 循环
                threshold_val, unit, op = repo.get_threshold(func.clause_id, building_type)  # 赋值
                func.threshold = threshold_val  # 赋值
                func.unit = unit  # 赋值
                func.operator = op  # 赋值
                r = func.execute(e)  # 赋值
                if r is None:  # 条件判断
                    continue  # 继续循环
                if r.result != "PASS":  # 条件判断
                    clause = {  # 赋值
                        "standard": "GB50016",  # 字段
                        "clause_id": func.clause_id,  # 字段
                        "title": func.name,  # 字段
                        "text": func.description,  # 字段
                        "category": func.category.value,  # 字段
                    }  # 闭合
                    f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])  # 赋值
                    details.append({  # 调用
                        "entity_id": e.get("id", e.get("type", "")),  # 字段
                        "entity_type": e["type"],  # 字段
                        "clause_id": f.clause.get("clause_id", ""),  # 字段
                        "clause_title": f.clause.get("title", ""),  # 字段
                        "result": f.judgement["result"],  # 字段
                        "extracted_value": f.extracted_params["extracted_value"],  # 字段
                        "required_value": f.extracted_params.get("required_value", 1.2),  # 字段
                        "difference": f.extracted_params.get("difference", 0),  # 字段
                        "explanation": f.explanation[:120],  # 字段
                    })  # 闭合

        # ── 缺失检查 ──────────────────────────────────────────
        for func in registry_funcs:  # 循环
            if func.category.value != "exist":  # 条件判断
                continue  # 继续循环
            has_match = any(func.matches(e) for e in entities)  # 赋值
            if not has_match:  # 条件判断
                r = func.execute(None)  # 赋值
                if r is not None and r.result != "PASS":  # 条件判断
                    clause = {  # 赋值
                        "standard": "GB50016",  # 字段
                        "clause_id": func.clause_id,  # 字段
                        "title": func.name,  # 字段
                        "text": func.description,  # 字段
                        "category": func.category.value,  # 字段
                    }  # 闭合
                    f = _attribution_analyzer.build_finding(r, clause, {}, entities[:5])  # 赋值
                    details.append({  # 调用
                        "entity_id": "",  # 字段
                        "entity_type": "missing",  # 字段
                        "clause_id": f.clause.get("clause_id", ""),  # 字段
                        "clause_title": f.clause.get("title", ""),  # 字段
                        "result": f.judgement["result"],  # 字段
                        "extracted_value": 0.0,  # 字段
                        "required_value": f.extracted_params.get("required_value", 1.0),  # 字段
                        "difference": -f.extracted_params.get("required_value", 1.0),  # 字段
                        "explanation": f.explanation[:120],  # 字段
                    })  # 闭合

        # ── 单文件统计 ────────────────────────────────────────
        entity_types = Counter(e["type"] for e in entities)  # 赋值
        violation_count = Counter(d["clause_id"] for d in details)  # 赋值

        file_result = {  # 赋值
            "filename": file.filename,  # 字段
            "file_id": file_id,  # 字段
            "status": "success",  # 字段
            "summary": {  # 字段
                "total_entities": len(entities),  # 字段
                "entity_types": dict(entity_types),  # 字段
                "violations": len(details),  # 字段
                "violation_by_clause": dict(violation_count.most_common(10)),  # 字段
            },  # 闭合
            "details": details[:100],  # 字段
            "entities": [  # 字段
                {"id": e.get("id", e.get("type", "")), "type": e["type"], "bbox": e["bbox"]}  # 字面量
                for e in entities  # 循环
            ],  # 闭合
        }  # 闭合

        all_details.extend(details)  # 调用
        all_entities.extend(entities)  # 调用
        total_violations += len(details)  # 赋值
        total_checks += len(entities) * len(registry_funcs)  # 赋值
        results.append(file_result)  # 调用

    # ── 交叉分析：跨图纸找出同一违规类别 ─────────────────────
    cross_clause = Counter(d["clause_id"] for d in all_details)  # 赋值
    cross_analysis = []  # 赋值
    for clause_id, count in cross_clause.most_common(10):  # 循环
        involved_files = set()  # 赋值
        for r in results:  # 循环
            if r["status"] != "success":  # 条件判断
                continue  # 继续循环
            for d in r["details"]:  # 遍历
                if d["clause_id"] == clause_id:  # 条件判断
                    involved_files.add(r["filename"])  # 调用
                    break  # 跳出循环
        cross_analysis.append({  # 调用
            "clause_id": clause_id,  # 字段
            "violations": count,  # 字段
            "files": len(involved_files),  # 字段
            "file_names": list(involved_files)[:5],  # 字段
        })  # 闭合

    elapsed = int((time.time() - start) * 1000)  # 赋值

    return {  # 返回
        "status": "success",  # 字段
        "batch_summary": {  # 字段
            "total_files": len(files),  # 字段
            "success_files": sum(1 for r in results if r["status"] == "success"),  # 字段
            "failed_files": sum(1 for r in results if r["status"] != "success"),  # 字段
            "total_violations": total_violations,  # 字段
            "total_checks": total_checks,  # 字段
            "total_entities": len(all_entities),  # 字段
            "processing_time_ms": elapsed,  # 字段
        },  # 闭合
        "cross_analysis": cross_analysis,  # 字段
        "results": results,  # 字段
    }  # 闭合


@app.post("/review-from-data")
async def review_from_data(
    body: dict,  # 操作
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
):  # 闭合
    """从已解析的结构化数据执行规范审查（无需重新上传文件）

    接收前端或其他服务已解析好的实体数据，直接运行规范判定。
    适用于已有结构化数据的场景，跳过图纸解析步骤。
    """
    entities = body.get("entities", [])  # 赋值
    building_type = body.get("building_type", "civil")  # 赋值

    from src.baa_engine.spec_repository import SpecRepository
    from collections import Counter
    repo = SpecRepository()  # 赋值
    clause_results = Counter()  # 赋值
    details = []  # 赋值
    registry_funcs = _func_registry.list_all()  # 赋值

    start = time.time()  # 赋值

    # ── 逐实体逐函数规范判定 ──────────────────────────────
    for e in entities:  # 循环
        for func in registry_funcs:  # 循环
            threshold_val, unit, op = repo.get_threshold(func.clause_id, building_type)  # 赋值
            func.threshold = threshold_val  # 赋值
            func.unit = unit  # 赋值
            func.operator = op  # 赋值
            r = func.execute(e)  # 赋值
            if r is None:  # 条件判断
                continue  # 继续循环
            clause_results[func.clause_id] += 1  # 赋值
            if r.result != "PASS":  # 条件判断
                clause = {  # 赋值
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # 闭合
                f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])  # 赋值
                details.append({  # 调用
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
                })  # 闭合

    # ── 缺失检查 ──────────────────────────────────────────
    for func in registry_funcs:  # 循环
        if func.category.value != "exist":  # 条件判断
            continue  # 继续循环
        has_match = any(func.matches(e) for e in entities)  # 赋值
        if not has_match:  # 条件判断
            r = func.execute(None)  # 赋值
            if r is not None and r.result != "PASS":  # 条件判断
                clause = {  # 赋值
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # 闭合
                f = _attribution_analyzer.build_finding(r, clause, {}, entities[:5])  # 赋值
                details.append({  # 调用
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
                })  # 闭合

    elapsed = int((time.time() - start) * 1000)  # 赋值
    entity_types = Counter(e["type"] for e in entities)  # 赋值
    violation_count = Counter(d["clause_id"] for d in details)  # 赋值

    response_data = {  # 赋值
        "status": "success",  # 字段
        "summary": {  # 字段
            "total_entities": len(entities),  # 字段
            "entity_types": dict(entity_types),  # 字段
            "total_checks": len(entities) * len(registry_funcs),  # 字段
            "violations": len(details),  # 字段
            "violation_by_clause": dict(violation_count.most_common(10)),  # 字段
        },  # 闭合
        "details": details[:100],  # 字段
        "building_type": building_type,  # 字段
        "processing_time_ms": elapsed,  # 字段
    }  # 闭合

    # ── 生成修正建议 ──────────────────────────────────────
    try:  # 尝试
        from src.baa_engine.correction_engine import CorrectionEngine
        ce = CorrectionEngine()  # 赋值
        review_result_for_correction = {  # 赋值
            "findings": [{  # 字段
                "entity_id": d["entity_id"],  # 字段
                "entity_type": d["entity_type"],  # 字段
                "clause_id": d["clause_id"],  # 字段
                "clause_title": d["clause_title"],  # 字段
                "extracted_value": d["extracted_value"],  # 字段
                "required_value": d["required_value"],  # 字段
                "difference": d["difference"],  # 字段
            } for d in details]  # 闭合
        }  # 闭合
        corrections = ce.generate_for_result(review_result_for_correction)  # 赋值
        response_data["corrections"] = corrections  # 操作
        # raw_result 供对比重构消费
        response_data["raw_result"] = {  # 操作
            "elements": elements,  # 字段
            "details": details,  # 字段
            "corrections": corrections,  # 字段
            "summary": response_data.get("summary", {}),  # 字段
        }  # 闭合
    except Exception as e:  # 捕获异常
        response_data["corrections"] = []  # 操作
        response_data["raw_result"] = {"elements": elements, "details": details}  # 操作

    return response_data  # 返回


@app.post("/reconstruct")
async def reconstruct(
    body: dict,  # 操作
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
):  # 闭合
    """BIM 重构（需授权验证）

    将已解析的审查结果重构为 IFC 格式的 BIM 模型文件。
    需要有效的 auth_token（通过支付获取）。
    """
    file_id = body.get("file_id", "")  # 赋值
    auth_token = body.get("auth_token", "")  # 赋值

    # ── 验证授权 ────────────────────────────────────────────
    auth_payload = verify_auth_token(auth_token)  # 赋值
    if auth_payload is None:  # 条件判断
        raise HTTPException(  # 抛出异常
            status_code=402,  # 赋值
            detail={  # 赋值
                "status": "error",  # 字段
                "error_code": "AUTH_FAILED",  # 字段
                "message": "支付授权验证失败，请确认订单已支付",  # 字段
            }  # 闭合
        )  # 闭合

    # ── 检查 file_id 是否存在 ───────────────────────────────
    file_path = get_file_path(file_id)  # 赋值
    if not file_path:  # 条件判断
        raise HTTPException(  # 抛出异常
            status_code=404,  # 赋值
            detail={  # 赋值
                "status": "error",  # 字段
                "error_code": "FILE_NOT_FOUND",  # 字段
                "message": f"文件不存在: {file_id}",  # 字段
            }  # 闭合
        )  # 闭合

    # ── 执行重构（暂返回 mock 数据） ─────────────────────────
    order_id = f"baa-order-{uuid.uuid4().hex[:8]}"  # 赋值
    model_path = MODELS_DIR / order_id  # 赋值
    model_path.mkdir(parents=True, exist_ok=True)  # 赋值
    (model_path / "model.ifc").write_text(  # 写入模型文件
        f"# Mock IFC file for order {order_id}\n"
        f"# Generated from file: {file_id}\n"
    )  # 闭合

    base_url = str(app.root_path) if app.root_path else "http://localhost:8000"  # 赋值

    return {  # 返回
        "status": "success",  # 字段
        "order_id": body.get("order_id", ""),  # 字段
        "baa_order_id": order_id,  # 字段
        "model_url": f"{base_url}/models/{order_id}/model.ifc",  # 字段
        "elements_count": 40,  # 字段
        "processing_time_ms": 15000,  # 字段
        "file_size_mb": 2.5,  # 字段
        "valid_until": (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z",  # 字段
    }  # 闭合


@app.get("/order/{order_id}")
async def get_order(
    order_id: str,  # 操作
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
):  # 闭合
    """订单状态查询

    查询 BIM 重构订单的处理状态和结果下载链接。
    """
    order_dir = MODELS_DIR / order_id  # 赋值
    if not order_dir.exists():  # 条件判断
        raise HTTPException(  # 抛出异常
            status_code=404,  # 赋值
            detail={  # 赋值
                "status": "error",  # 字段
                "error_code": "ORDER_NOT_FOUND",  # 字段
                "message": "订单不存在",  # 字段
            }  # 闭合
        )  # 闭合

    model_file = order_dir / "model.ifc"  # 赋值
    if model_file.exists():  # 条件判断
        return {  # 返回
            "status": "completed",  # 字段
            "order_id": order_id,  # 字段
            "progress": 100,  # 字段
            "model_url": f"/models/{order_id}/model.ifc",  # 字段
            "file_size_mb": round(model_file.stat().st_size / 1024 / 1024, 2),  # 字段
        }  # 闭合
    else:  # 否则
        return {  # 返回
            "status": "processing",  # 字段
            "order_id": order_id,  # 字段
            "progress": 50,  # 字段
            "estimated_remaining_ms": 15000,  # 字段
        }  # 闭合


# ── 图纸渲染 ──────────────────────────────────────────────


@app.get("/render/{file_id}")
async def render_drawing(
    file_id: str,  # 操作
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
):  # 闭合
    """将 DXF/DWG 图纸渲染为 SVG 供前端展示

    从存储的 DWG/DXF 文件中提取图元，生成缩放适配的 SVG 预览图。
    支持 LINE、LWPOLYLINE、CIRCLE、TEXT/MTEXT 等图元类型。
    最多渲染 2000 个图元以避免超时。
    """
    file_path = get_file_path(file_id)  # 赋值
    if not file_path:  # 条件判断
        raise HTTPException(status_code=404, detail={"status": "error", "message": "文件不存在"})  # 抛出异常

    import ezdxf
    from io import StringIO

    try:  # 尝试
        doc = ezdxf.readfile(str(file_path))  # 赋值
        msp = doc.modelspace()  # 赋值
    except Exception:  # 捕获异常
        raise HTTPException(status_code=400, detail={"status": "error", "message": "无法解析图纸文件"})  # 抛出异常

    # ── 计算图元边界（用于 SVG viewBox 适配） ────────────────
    all_x, all_y = [], []  # 赋值
    for entity in msp:  # 循环
        try:  # 尝试
            if entity.dxftype() == "LINE":  # 条件判断
                s, e = entity.dxf.start, entity.dxf.end  # 赋值
                all_x.extend([s[0], e[0]])  # 调用
                all_y.extend([s[1], e[1]])  # 调用
            elif entity.dxftype() == "LWPOLYLINE":  # 分支
                pts = [(v[0], v[1]) for v in entity.get_points()]  # 赋值
                all_x.extend(p[0] for p in pts)  # 调用
                all_y.extend(p[1] for p in pts)  # 调用
            elif entity.dxftype() == "CIRCLE":  # 分支
                cx, cy = entity.dxf.center[:2]  # 赋值
                r = entity.dxf.radius  # 赋值
                all_x.extend([cx - r, cx + r])  # 调用
                all_y.extend([cy - r, cy + r])  # 调用
            elif entity.dxftype() in ("TEXT", "MTEXT"):  # 分支
                ins = entity.dxf.insert[:2]  # 赋值
                all_x.append(ins[0])  # 调用
                all_y.append(ins[1])  # 调用
        except Exception:  # 捕获异常
            continue  # 继续循环

    if not all_x:  # 条件判断
        return {"status": "error", "message": "图纸无有效图元"}  # 返回

    # ── 计算 SVG viewBox 参数 ────────────────────────────────
    margin = 5.0  # 赋值
    x_min, x_max = min(all_x) - margin, max(all_x) + margin  # 解包
    y_min, y_max = min(all_y) - margin, max(all_y) + margin  # 解包
    w, h = x_max - x_min, y_max - y_min  # 赋值

    svg_w = min(max(w * 0.5, 400), 1200)    # SVG 输出宽度
    svg_h = min(max(h * 0.5, 300), 800)      # SVG 输出高度

    # ── 构建 SVG 字符串 ──────────────────────────────────────
    buf = StringIO()  # 赋值
    buf.write(f'<svg xmlns="http://www.w3.org/2000/svg" '  # 调用
              f'viewBox="{x_min} {-y_max} {w} {h}" '  # 操作
              f'width="{svg_w}" height="{svg_h}" '  # 操作
              f'style="background:#fff">\n')

    max_entities = 2000  # 渲染上限，避免大图纸超时
    drawn = 0  # 赋值

    for entity in msp:  # 循环
        if drawn >= max_entities:  # 条件判断
            break  # 跳出循环
        dxftype = entity.dxftype()  # 赋值
        try:  # 尝试
            if dxftype == "LINE":  # 条件判断
                s, e = entity.dxf.start, entity.dxf.end  # 赋值
                buf.write(f'<line x1="{s[0]:.2f}" y1="{-s[1]:.2f}" '  # 调用
                          f'x2="{e[0]:.2f}" y2="{-e[1]:.2f}" '  # 操作
                          f'stroke="#333" stroke-width="0.5" />\n')
                drawn += 1  # 赋值
            elif dxftype == "LWPOLYLINE":  # 分支
                pts = [(v[0], -v[1]) for v in entity.get_points()]  # 赋值
                d = "M" + " L".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts)  # 赋值
                buf.write(f'<path d="{d}" fill="none" stroke="#333" stroke-width="0.5" />\n')
                drawn += 1  # 赋值
            elif dxftype == "CIRCLE":  # 分支
                cx, cy = entity.dxf.center[:2]  # 赋值
                r = entity.dxf.radius  # 赋值
                buf.write(f'<circle cx="{cx:.2f}" cy="{-cy:.2f}" r="{r:.2f}" '  # 调用
                          f'fill="none" stroke="#333" stroke-width="0.5" />\n')
                drawn += 1  # 赋值
            elif dxftype in ("TEXT", "MTEXT"):  # 分支
                ins = entity.dxf.insert[:2]  # 赋值
                txt = entity.dxf.text if hasattr(entity.dxf, 'text') else ''  # 赋值
                ht = entity.dxf.height if hasattr(entity.dxf, 'height') else 2.5  # 赋值
                buf.write(f'<text x="{ins[0]:.2f}" y="{-ins[1]:.2f}" '  # 调用
                          f'font-size="{ht}" fill="#666">{txt[:30]}</text>\n')
                drawn += 1  # 赋值
        except Exception:  # 捕获异常
            continue  # 继续循环

    buf.write('</svg>')  # 调用
    svg_content = buf.getvalue()  # 赋值

    return Response(content=svg_content, media_type="image/svg+xml")  # 返回


# ── 静态文件服务（模型下载） ─────────────────────────────

SPECS_DIR = DATA_DIR / "specs"  # 赋值

if SPECS_DIR.exists():  # 条件判断
    app.mount("/data/specs", StaticFiles(directory=str(SPECS_DIR)), name="specs")  # 调用

if MODELS_DIR.exists():  # 条件判断
    app.mount("/models", StaticFiles(directory=str(MODELS_DIR)), name="models")  # 调用


# ── API密钥管理端点 ──────────────────────────────────


@app.post("/admin/keys", tags=["admin"])
async def create_api_key(
    body: dict,  # 操作
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
    _admin: str = Depends(require_admin),  # 赋值
):  # 闭合
    """创建新的API Key（需要admin权限）"""
    km = get_key_manager()  # 赋值

    permission = body.get("permission", "write")  # 赋值
    ttl_days = body.get("ttl_days", 90)  # 赋值
    label = body.get("label", "")  # 赋值

    try:  # 尝试
        result = km.generate_key(  # 赋值
            permission=permission,  # 赋值
            ttl_days=ttl_days,  # 赋值
            label=label,  # 赋值
            created_by=api_key or "anonymous"  # 赋值
        )  # 闭合
    except ValueError as e:  # 捕获异常
        raise HTTPException(status_code=400, detail={  # 抛出异常
            "status": "error", "error_code": "INVALID_PARAM",  # 字段
            "message": str(e)  # 字段
        })  # 闭合

    return {  # 返回
        "status": "success",  # 字段
        "data": result,  # 字段
        "warning": "请立即保存 raw_key，创建后不再显示",  # 字段
    }  # 闭合


@app.get("/admin/keys", tags=["admin"])
async def list_api_keys(
    include_disabled: bool = Query(False),  # 赋值
    include_raw: bool = Query(False, description="是否返回解密后的 raw_key（密钥详情时使用）"),  # 赋值
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
    _admin: str = Depends(require_admin),  # 赋值
):  # 闭合
    """列出所有API Key"""
    km = get_key_manager()  # 赋值
    keys = km.list_keys(include_disabled=include_disabled, include_raw=include_raw)  # 赋值
    stats = km.get_usage_stats()  # 赋值

    for k in keys:  # 循环
        k_id = k["key_id"]  # 赋值
        if k_id in stats:  # 条件判断
            k["usage"] = stats[k_id]  # 操作

    return {  # 返回
        "status": "success",  # 字段
        "data": keys,  # 字段
        "total": len(keys),  # 字段
    }  # 闭合


@app.get("/admin/keys/stats", tags=["admin"])
async def api_key_stats(
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
    _admin: str = Depends(require_admin),  # 赋值
):  # 闭合
    """API Key用量统计"""
    km = get_key_manager()  # 赋值

    stats = km.get_usage_stats()  # 赋值
    keys = km.list_keys(include_disabled=True)  # 赋值

    return {  # 返回
        "status": "success",  # 字段
        "data": {  # 字段
            "keys": stats,  # 字段
            "summary": {  # 字段
                "total": len(keys),  # 字段
                "active": len([k for k in keys if k.get("enabled")]),  # 字段
                "disabled": len([k for k in keys if not k.get("enabled")]),  # 字段
                "total_calls": sum(s.get("total_calls", 0) for s in stats.values()),  # 字段
            }  # 闭合
        }  # 闭合
    }  # 闭合


@app.get("/admin/keys/{key_id}", tags=["admin"])
async def get_api_key_detail(
    key_id: str,  # 操作
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
    _admin: str = Depends(require_admin),  # 赋值
):  # 闭合
    """获取单个API Key详情（含解密后的 raw_key）"""
    km = get_key_manager()  # 赋值
    keys = km.list_keys(include_disabled=True, include_raw=True)  # 赋值
    for k in keys:  # 循环
        if k["key_id"] == key_id:  # 条件判断
            stats = km.get_usage_stats(key_id)  # 赋值
            k["usage"] = stats  # 操作
            return {"status": "success", "data": k}  # 返回
    raise HTTPException(status_code=404, detail={  # 抛出异常
        "status": "error", "error_code": "NOT_FOUND",  # 字段
        "message": f"密钥不存在: {key_id}"  # 字段
    })  # 闭合


@app.post("/admin/keys/{key_id}/revoke", tags=["admin"])
async def revoke_api_key(
    key_id: str,  # 操作
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
    _admin: str = Depends(require_admin),  # 赋值
):  # 闭合
    """撤销API Key"""
    km = get_key_manager()  # 赋值

    if km.revoke_key(key_id):  # 条件判断
        return {"status": "success", "message": f"密钥 {key_id} 已撤销"}  # 返回
    raise HTTPException(status_code=404, detail={  # 抛出异常
        "status": "error", "error_code": "NOT_FOUND",  # 字段
        "message": f"密钥不存在: {key_id}"  # 字段
    })  # 闭合


@app.post("/admin/keys/{key_id}/rotate", tags=["admin"])
async def rotate_api_key(
    key_id: str,  # 操作
    body: dict,  # 操作
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
    _admin: str = Depends(require_admin),  # 赋值
):  # 闭合
    """轮换API Key（生成新密钥值，旧密钥失效）"""
    km = get_key_manager()  # 赋值
    result = km.rotate_key(key_id, new_ttl_days=new_ttl)  # 赋值
    if result:  # 条件判断
        return {  # 返回
            "status": "success",  # 字段
            "data": result,  # 字段
            "warning": "旧密钥已失效，请立即保存新 raw_key",  # 字段
        }  # 闭合
    raise HTTPException(status_code=404, detail={  # 抛出异常
        "status": "error", "error_code": "NOT_FOUND",  # 字段
        "message": f"密钥不存在或已禁用: {key_id}"  # 字段
    })  # 闭合


@app.delete("/admin/keys/{key_id}", tags=["admin"])
async def delete_api_key(
    key_id: str,  # 操作
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
    _admin: str = Depends(require_admin),  # 赋值
):  # 闭合
    """物理删除API Key（不可恢复）"""
    km = get_key_manager()  # 赋值
    if km.delete_key(key_id):  # 条件判断
        return {"status": "success", "message": f"密钥 {key_id} 已永久删除"}  # 返回
    raise HTTPException(status_code=404, detail={  # 抛出异常
        "status": "error", "error_code": "NOT_FOUND",  # 字段
        "message": f"密钥不存在: {key_id}"  # 字段
    })  # 闭合


@app.post("/admin/keys/verify", tags=["admin"])
async def verify_api_key_raw(
    body: dict,  # 操作
    request: Request = None,  # 赋值
):  # 闭合
    """验证原始API Key是否有效（无需admin权限，供前端导入时校验）"""
    raw_key = body.get("raw_key", "")  # 赋值
    if not raw_key:  # 条件判断
        return {"status": "error", "valid": False, "message": "请提供 raw_key"}  # 返回

    km = get_key_manager()  # 赋值
    key_info = km.validate_key(raw_key)  # 赋值
    if key_info and key_info.get("enabled", True):  # 条件判断
        return {  # 返回
            "status": "success",  # 字段
            "valid": True,  # 字段
            "key_info": {  # 字段
                "key_id": key_info.get("key_id"),  # 字段
                "label": key_info.get("label"),  # 字段
                "permission": key_info.get("permission"),  # 字段
                "expires_at": key_info.get("expires_at"),  # 字段
                "created_at": key_info.get("created_at"),  # 字段
            }  # 闭合
        }  # 闭合
    else:  # 否则
        return {  # 返回
            "status": "success",  # 字段
            "valid": False,  # 字段
            "message": "密钥无效或已过期/撤销"  # 字段
        }  # 闭合


@app.get("/admin/bootstrap-key", tags=["admin"])
async def bootstrap_admin_key():
    """获取前端密钥管理页使用的管理令牌（免认证）
    
    开发模式（BAA_API_KEY 未设置）时返回空字符串，
    此时后端 require_admin 不校验令牌，前端直接发请求即可。
    生产模式时返回环境变量中的 admin key。
    """
    env_key = os.getenv("BAA_API_KEY", "")  # 赋值
    return {  # 返回
        "status": "success",  # 字段
        "admin_key": env_key,  # 字段
        "mode": "production" if env_key else "development",  # 字段
    }  # 闭合


# ── EMA2 第三方对接 API ───────────────────────────────────

async def _fire_webhook(webhook_url: str, payload: dict) -> bool:
    """发送 Webhook 回调通知（异步，不阻塞主流程）

    Args:
        webhook_url: 回调目标 URL
        payload: 发送的 JSON 数据

    Returns:
        bool: 是否发送成功
    """
    import httpx
    try:  # 尝试
        async with httpx.AsyncClient(timeout=10.0) as client:  # 赋值
            resp = await client.post(webhook_url, json=payload)  # 赋值
            return resp.status_code == 200  # 返回
    except Exception:  # 捕获异常
        return False  # 返回


async def _run_review_task(task_id: str, file_path: str, building_type: str, webhook_url: str = None):
    """后台执行异步审查任务

    在后台线程中执行完整的审查流程：解析→语义分析→规范判定→缺失检查。
    完成后更新 _tasks 存储中的状态，并根据配置触发 Webhook 回调。
    """
    _tasks[task_id]["status"] = "running"  # 操作
    _tasks[task_id]["updated_at"] = datetime.now().isoformat()  # 操作
    
    try:  # 尝试
        start = time.time()  # 赋值
        loop = asyncio.get_event_loop()  # 赋值
        
        # ── Step 1: 图纸解析 ─────────────────────────────────
        result = await loop.run_in_executor(  # 赋值
            ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), task_id  # 操作
        )  # 闭合
        if not result.success:  # 条件判断
            _tasks[task_id]["status"] = "failed"  # 操作
            _tasks[task_id]["error"] = f"解析失败: {result.error}"  # 操作
            _tasks[task_id]["updated_at"] = datetime.now().isoformat()  # 操作
            if webhook_url:  # 条件判断
                await _fire_webhook(webhook_url, {  # 操作
                    "task_id": task_id, "status": "failed", "error": _tasks[task_id]["error"]  # 字段
                })  # 闭合
            return  # 返回
        
        # ── Step 2: 语义分析 ─────────────────────────────────
        semantic = await loop.run_in_executor(  # 赋值
            ENGINE_THREAD_POOL,  # 解包
            lambda: _semantic_analyzer.analyze(  # 操作
                result.primitives, result.dimensions, building_type=building_type  # 解包
            )  # 闭合
        )  # 闭合
        entities = semantic["entities"]  # 赋值
        
        # ── Step 3: 规范判定 ─────────────────────────────────
        details = []  # 赋值
        for e in entities:  # 循环
            for func in _func_registry.list_all():  # 循环
                threshold_val, unit, op = _spec_repo.get_threshold(func.clause_id, building_type)  # 赋值
                func.threshold = threshold_val  # 赋值
                func.unit = unit  # 赋值
                func.operator = op  # 赋值
                r = func.execute(e)  # 赋值
                if r is None or r.result == "PASS":  # 条件判断
                    continue  # 继续循环
                clause = {  # 赋值
                    "standard": "GB50016",  # 字段
                    "clause_id": func.clause_id,  # 字段
                    "title": func.name,  # 字段
                    "text": func.description,  # 字段
                    "category": func.category.value,  # 字段
                }  # 闭合
                f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])  # 赋值
                details.append({  # 调用
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
                })  # 闭合
        
        # ── Step 4: 缺失检查 ─────────────────────────────────
        for func in _func_registry.list_all():  # 循环
            if func.category.value != "exist":  # 条件判断
                continue  # 继续循环
            if not any(func.matches(e) for e in entities):  # 条件判断
                r = func.execute(None)  # 赋值
                if r is not None and r.result != "PASS":  # 条件判断
                    clause = {  # 赋值
                        "standard": "GB50016",  # 字段
                        "clause_id": func.clause_id,  # 字段
                        "title": func.name,  # 字段
                        "text": func.description,  # 字段
                        "category": func.category.value,  # 字段
                    }  # 闭合
                    f = _attribution_analyzer.build_finding(r, clause, {}, entities[:5])  # 赋值
                    details.append({  # 调用
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
                    })  # 闭合
        
        elapsed = int((time.time() - start) * 1000)  # 赋值
        
        # ── 存储结果 ────────────────────────────────────────
        _tasks[task_id]["status"] = "completed"  # 操作
        _tasks[task_id]["result"] = {  # 操作
            "summary": {  # 字段
                "total_entities": len(entities),  # 字段
                "violations": len(details),  # 字段
                "entity_types": dict(Counter(e["type"] for e in entities)),  # 字段
            },  # 闭合
            "details": details,  # 字段
            "processing_time_ms": elapsed,  # 字段
        }  # 闭合
        _tasks[task_id]["updated_at"] = datetime.now().isoformat()  # 操作
        
        # ── Webhook 回调通知 ─────────────────────────────────
        if webhook_url:  # 条件判断
            await _fire_webhook(webhook_url, {  # 操作
                "task_id": task_id, "status": "completed",  # 字段
                "violations": len(details), "entities": len(entities),  # 字段
                "processing_time_ms": elapsed,  # 字段
            })  # 闭合
    
    except Exception as e:  # 捕获异常
        _tasks[task_id]["status"] = "failed"  # 操作
        _tasks[task_id]["error"] = str(e)  # 操作
        _tasks[task_id]["updated_at"] = datetime.now().isoformat()  # 操作
        if webhook_url:  # 条件判断
            await _fire_webhook(webhook_url, {  # 操作
                "task_id": task_id, "status": "failed", "error": str(e)  # 字段
            })  # 闭合


@app.post("/api/v1/tasks", tags=["EMA2"])
async def create_review_task(
    file: UploadFile = File(...),  # 赋值
    building_type: str = Query("civil", description="建筑类型: civil/industrial"),  # 赋值
    webhook_url: str = Query("", description="回调通知 URL（可选）"),  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
):  # 闭合
    """创建异步审查任务（EMA2 对接）
    
    上传图纸文件，创建异步审查任务。任务完成后通过轮询或 Webhook 获取结果。
    """
    filename = file.filename or "unknown"  # 赋值
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""  # 赋值
    if ext not in SUPPORTED_FORMATS:  # 条件判断
        raise HTTPException(status_code=400, detail={  # 抛出异常
            "status": "error", "error_code": "UNSUPPORTED_FORMAT",  # 字段
            "message": f"不支持的文件格式: {ext}",  # 字段
        })  # 闭合
    
    content = await file.read()  # 赋值
    if len(content) > MAX_FILE_SIZE:  # 条件判断
        raise HTTPException(status_code=400, detail={  # 抛出异常
            "status": "error", "error_code": "FILE_TOO_LARGE",  # 字段
            "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",  # 字段
        })  # 闭合
    
    file_id = generate_file_id()  # 赋值
    file_path = store_file(content, file_id, ext)  # 赋值
    
    # 创建任务
    task_id = str(uuid.uuid4())[:8]  # 赋值
    _tasks[task_id] = {  # 赋值
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
    }  # 闭合
    
    # 启动后台任务
    asyncio.create_task(_run_review_task(task_id, str(file_path), building_type, webhook_url))  # 调用
    
    return {  # 返回
        "status": "success",  # 字段
        "task_id": task_id,  # 字段
        "status_url": f"/api/v1/tasks/{task_id}",  # 字段
        "result_url": f"/api/v1/tasks/{task_id}/result",  # 字段
    }  # 闭合


@app.get("/api/v1/tasks/{task_id}", tags=["EMA2"])
async def get_task_status(task_id: str, api_key: str = Depends(verify_api_key)):
    """查询任务状态（EMA2 对接）"""
    task = _tasks.get(task_id)  # 赋值
    if not task:  # 条件判断
        raise HTTPException(status_code=404, detail={  # 抛出异常
            "status": "error", "error_code": "TASK_NOT_FOUND",  # 字段
            "message": f"任务不存在: {task_id}",  # 字段
        })  # 闭合
    
    return {  # 返回
        "status": "success",  # 字段
        "task_id": task_id,  # 字段
        "state": task["status"],  # 字段
        "filename": task.get("filename"),  # 字段
        "created_at": task.get("created_at"),  # 字段
        "updated_at": task.get("updated_at"),  # 字段
        "error": task.get("error"),  # 字段
    }  # 闭合


@app.get("/api/v1/tasks/{task_id}/result", tags=["EMA2"])
async def get_task_result(task_id: str, api_key: str = Depends(verify_api_key)):
    """获取审查结果（EMA2 对接）"""
    task = _tasks.get(task_id)  # 赋值
    if not task:  # 条件判断
        raise HTTPException(status_code=404, detail={  # 抛出异常
            "status": "error", "error_code": "TASK_NOT_FOUND",  # 字段
            "message": f"任务不存在: {task_id}",  # 字段
        })  # 闭合
    
    if task["status"] == "pending":  # 条件判断
        raise HTTPException(status_code=409, detail={  # 抛出异常
            "status": "pending",  # 字段
            "message": "任务仍在处理中，请稍后查询",  # 字段
        })  # 闭合
    
    if task["status"] == "failed":  # 条件判断
        raise HTTPException(status_code=500, detail={  # 抛出异常
            "status": "error", "error_code": "TASK_FAILED",  # 字段
            "message": task.get("error", "任务执行失败"),  # 字段
        })  # 闭合
    
    return {  # 返回
        "status": "success",  # 字段
        "task_id": task_id,  # 字段
        "result": task.get("result"),  # 字段
    }  # 闭合


@app.post("/api/v1/webhooks", tags=["EMA2"])
async def register_webhook(
    url: str = Query(..., description="回调 URL"),  # 赋值
    events: str = Query("completed", description="触发事件: completed,failed,all"),  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
):  # 闭合
    """注册 Webhook 回调（EMA2 对接）

    注册后，当异步审查任务完成或失败时，系统会 POST 通知到该 URL。
    """
    webhook_id = str(uuid.uuid4())[:8]  # 赋值
    _webhooks[webhook_id] = {  # 赋值
        "webhook_id": webhook_id,  # 字段
        "url": url,  # 字段
        "events": events,  # 字段
        "active": True,  # 字段
        "created_at": datetime.now().isoformat(),  # 字段
    }  # 闭合
    return {  # 返回
        "status": "success",  # 字段
        "webhook_id": webhook_id,  # 字段
        "url": url,  # 字段
        "events": events,  # 字段
    }  # 闭合


@app.get("/api/v1/webhooks", tags=["EMA2"])
async def list_webhooks(api_key: str = Depends(verify_api_key)):
    """查询 Webhook 列表（EMA2 对接）"""
    return {  # 返回
        "status": "success",  # 字段
        "webhooks": list(_webhooks.values()),  # 字段
    }  # 闭合


@app.delete("/api/v1/webhooks/{webhook_id}", tags=["EMA2"])
async def delete_webhook(webhook_id: str, api_key: str = Depends(verify_api_key)):
    """删除 Webhook（EMA2 对接）"""
    if webhook_id not in _webhooks:  # 条件判断
        raise HTTPException(status_code=404, detail={  # 抛出异常
            "status": "error", "error_code": "WEBHOOK_NOT_FOUND",  # 字段
            "message": f"Webhook 不存在: {webhook_id}",  # 字段
        })  # 闭合
    del _webhooks[webhook_id]  # 删除
    return {"status": "success", "message": "Webhook 已删除"}  # 返回


# ── P10 反馈闭环 API ───────────────────────────────────────

@app.post("/api/v1/feedbacks", tags=["Feedback"])
async def submit_feedback(body: dict):
    """提交违规申诉（P10 反馈闭环）

    用户对审查结果有异议时，提交申诉。
    Body 包含 task_id, clause_id, entity_id, entity_type, reason, description 等。
    申诉数据后续用于模型微调，减少误报。
    """
    record = _feedback_manager.submit(  # 赋值
        task_id=body.get("task_id", ""),  # 赋值
        clause_id=body.get("clause_id", ""),  # 赋值
        entity_id=body.get("entity_id", ""),  # 赋值
        entity_type=body.get("entity_type", ""),  # 赋值
        reason=body.get("reason", ""),  # 赋值
        description=body.get("description", ""),  # 赋值
        original_value=body.get("original_value"),  # 赋值
        severity=body.get("severity", ""),  # 赋值
    )  # 闭合
    return {"status": "success", "feedback": record}  # 返回


@app.get("/api/v1/feedbacks", tags=["Feedback"])
async def list_feedbacks(
    status: str = Query("", description="筛选状态: pending/accepted/rejected"),  # 赋值
    clause_id: str = Query("", description="筛选规范条款"),  # 赋值
    limit: int = Query(50, ge=1, le=200),  # 赋值
    offset: int = Query(0, ge=0),  # 赋值
):  # 闭合
    """查询申诉列表（支持状态和规范条款筛选）"""
    items, total = _feedback_manager.list_all(  # 赋值
        status=status, clause_id=clause_id, limit=limit, offset=offset  # 赋值
    )  # 闭合
    return {"status": "success", "feedbacks": items, "total": total}  # 返回


@app.get("/api/v1/feedbacks/stats", tags=["Feedback"])
async def feedback_stats():
    """申诉统计（总数、待处理数、各类分布）"""
    return {"status": "success", "stats": _feedback_manager.stats()}  # 返回


@app.get("/api/v1/feedbacks/{feedback_id}", tags=["Feedback"])
async def get_feedback(feedback_id: str):
    """查询单条申诉详情"""
    record = _feedback_manager.get(feedback_id)  # 赋值
    if not record:  # 条件判断
        raise HTTPException(status_code=404, detail={  # 抛出异常
            "status": "error", "error_code": "FEEDBACK_NOT_FOUND",  # 字段
            "message": f"申诉不存在: {feedback_id}",  # 字段
        })  # 闭合
    return {"status": "success", "feedback": record}  # 返回


@app.patch("/api/v1/feedbacks/{feedback_id}", tags=["Feedback"])
async def review_feedback(
    feedback_id: str,  # 操作
    body: dict,  # 操作
):  # 闭合
    """审核申诉（P10 反馈闭环）

    管理员审核用户提交的申诉。
    Body: {status: accepted/rejected, reviewed_by, review_comment?}
    """
    record = _feedback_manager.review(  # 赋值
        feedback_id, body.get("status", ""), body.get("reviewed_by", ""),  # 操作
        body.get("review_comment", "")  # 调用
    )  # 闭合
    if not record:  # 条件判断
        raise HTTPException(status_code=404, detail={  # 抛出异常
            "status": "error", "error_code": "FEEDBACK_NOT_FOUND",  # 字段
            "message": f"申诉不存在: {feedback_id}",  # 字段
        })  # 闭合
    return {"status": "success", "feedback": record}  # 返回


@app.post("/api/v1/feedbacks/{feedback_id}/adjust", tags=["Feedback"])
async def adjust_threshold(
    feedback_id: str,  # 操作
    body: dict,  # 操作
):  # 闭合
    """基于申诉数据计算/应用阈值调整

    使用 LearningEngine 分析申诉数据，计算建议的阈值调整值。
    如果 apply=true，直接应用调整到规范知识库。
    Body: {clause_id, apply?}
    """
    clause_id = body.get("clause_id", "")  # 赋值
    apply = body.get("apply", False)  # 赋值
    
    try:  # 尝试
        current, unit, op = _spec_repo.get_threshold(clause_id, "civil")  # 操作
    except ValueError:  # 捕获异常
        raise HTTPException(status_code=404, detail={  # 抛出异常
            "status": "error", "error_code": "CLAUSE_NOT_FOUND",  # 字段
            "message": f"规范不存在: {clause_id}",  # 字段
        })  # 闭合

    adjustment = _learning_engine.compute_adjustment(clause_id, current)  # 赋值

    if apply and adjustment.get("adjustable"):  # 条件判断
        success = _learning_engine.apply_adjustment(  # 赋值
            clause_id, adjustment["suggested_threshold"], _spec_repo,  # 操作
            reason=f"基于申诉 {feedback_id} 的自动微调"  # 赋值
        )  # 闭合
        adjustment["applied"] = success  # 操作

    return {"status": "success", "adjustment": adjustment}  # 返回


# ── 启动入口 ──────────────────────────────────────────────

if __name__ == "__main__":  # 条件判断
    """直接运行本文件时启动 Uvicorn 服务器

    生产环境建议通过 Docker 或 systemd 管理进程生命周期。
    """
    import uvicorn
    import sys
    import os
    port = int(os.getenv("BAA_PORT", "8000"))       # 服务端口
    workers = int(os.getenv("BAA_WORKERS", "4"))    # 默认4 worker

    # 日志输出到项目 data/logs/ 下
    log_dir = DATA_DIR / "logs"  # 赋值
    log_dir.mkdir(parents=True, exist_ok=True)  # 赋值
    log_file = log_dir / "baa-api.log"  # 赋值
    print(f"[BAA] 日志路径: {log_file}", flush=True)  # 调用
    print(f"[BAA] Worker 数: {workers}", flush=True)  # 调用

    uvicorn.run(  # 调用
        "src.api.baa_api:app",  # 应用模块路径
        host="0.0.0.0",  # 赋值
        port=port,  # 赋值
        workers=workers,  # 赋值
        log_config=None,  # 赋值
        access_log=False,  # 赋值
        log_level="info"  # 赋值
    )  # 闭合
