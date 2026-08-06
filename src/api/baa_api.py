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
from __future__ import (
    annotations,
)  # noqa: F401 必须在所有 import 之前，保证 Optional 等类型注解可用
import time  # 时间戳、超时控制
import gc  # 垃圾回收
import json  # JSON 序列化/反序列化
import hmac  # HMAC 签名
import hashlib  # 哈希函数
import base64  # Base64 编码
from datetime import datetime  # 日期时间处理

# ── FastAPI 及依赖 ──────────────────────────────────────────
from fastapi import (
    FastAPI,
    File,
    UploadFile,
    HTTPException,
    Depends,
    Query,
    Request,
)  # fastapi: HTTP framework
from fastapi.security import HTTPBearer  # import
from fastapi.middleware.cors import CORSMiddleware  # import
from fastapi.staticfiles import StaticFiles  # import

# ═══════════════════════════════════════════════════════════════
# 共享全局变量与工具函数
# ═══════════════════════════════════════════════════════════════
from src.api.api_globals import *  # noqa: F401, F403

# ── 反馈引擎（在 globals 中延迟导入，这里显式导入供类型注解用）
from src.baa_engine.feedback_engine import FeedbackManager, LearningEngine  # import


def _sanitize_for_json(obj):
    """递归清理 numpy 类型和不可序列化对象，避免 FastAPI jsonable_encoder 报错。

    处理：
    - numpy.bool_ → bool
    - numpy.int* / numpy.float* → int / float
    - 无 __dict__ 的对象 → 字符串
    - 嵌套 dict / list 递归处理
    """
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    try:
        import numpy as _np

        if isinstance(obj, _np.bool_):
            return bool(obj)
        if isinstance(obj, _np.integer):
            return int(obj)
        if isinstance(obj, _np.floating):
            return float(obj)
        if isinstance(obj, _np.ndarray):
            return obj.tolist()
    except ImportError:
        pass
    if isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    if hasattr(obj, "__dict__"):
        return obj
    return str(obj)


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


def _load_engine_sync():  # function: def _load_engine_sync():
    """同步预热加载引擎模块，每个 worker 启动时执行一次

    注意：必须使用 sys.modules[__name__] 操作模块 __dict__，
    而不是 global 声明。因为 _load_engine_sync 从 daemon 线程
    或 from-import 调用时，global 会绑定到 __main__ 而非 baa_api 模块。
    """
    import sys as _sys  # stdlib: sys

    try:
        from src.baa_engine.drawing_parser import DrawingParser  # import
        from src.baa_engine.semantic_analyzer import SemanticAnalyzer  # import
        from src.baa_engine.atomic_functions import FuncRegistry  # import
        from src.baa_engine.attribution_analyzer import AttributionAnalyzer  # import
        from src.baa_engine.spec_repository import SpecRepository  # import

        _drawing_parser = DrawingParser()  # function call
        _semantic_analyzer = SemanticAnalyzer()  # function call
        _func_registry = FuncRegistry()  # function call
        _attribution_analyzer = AttributionAnalyzer()  # function call
        _spec_repo = SpecRepository()  # function call
        _feedback_manager = FeedbackManager(DATA_DIR)  # function call
        _learning_engine = LearningEngine(_feedback_manager)  # function call

        # 通过 setattr 写入 baa_api 模块，保证任何调用路径（daemon 线程 / from-import）
        # 都能正确更新模块级全局变量。global 声明在 from-import 场景下会绑定到
        # __main__ 的命名空间，导致状态丢失。
        _m = _sys.modules[__name__]  # 当前 baa_api 模块
        setattr(_m, "_drawing_parser", _drawing_parser)
        setattr(_m, "_semantic_analyzer", _semantic_analyzer)
        setattr(_m, "_func_registry", _func_registry)
        setattr(_m, "_attribution_analyzer", _attribution_analyzer)
        setattr(_m, "_spec_repo", _spec_repo)
        setattr(_m, "_feedback_manager", _feedback_manager)
        setattr(_m, "_learning_engine", _learning_engine)
        setattr(_m, "_engine_ready", True)  # 标记引擎就绪

        # 同步到 api_globals 供 review_routes 等子模块使用
        import src.api.api_globals as _ag  # import

        _ag._drawing_parser = _drawing_parser
        _ag._semantic_analyzer = _semantic_analyzer
        _ag._func_registry = _func_registry
        _ag._attribution_analyzer = _attribution_analyzer
        _ag._spec_repo = _spec_repo
        _ag._feedback_manager = _feedback_manager
        _ag._learning_engine = _learning_engine
        print(
            f"[BAA] 引擎已预热: {_func_registry.count}个原子函数, {_spec_repo.count}条规范"
        )  # print output
        print(f"[BAA] 反馈闭环已加载: {_feedback_manager.stats()['total']}条申诉")  # print output
    except Exception as e:
        import traceback

        print(f"[BAA] 引擎预热失败: {e}")
        traceback.print_exc()


from contextlib import asynccontextmanager  # import

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


# ── 并发限制与审查任务队列（在 api_globals 中定义） ──
import asyncio  # stdlib: async

# 兼容旧引用（_review_semaphore 保留为旧代码引用用，但不再使用）
_review_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REVIEWS)


# 预热加载引擎（同步执行，用 timeout 防止阻塞 worker 启动）
import threading  # import

# 必须先初始化变量，再启动线程，否则线程中 setattr 写入会被下方 = None 覆盖
_drawing_parser = None  # 图纸解析器
_engine_ready = False  # 引擎就绪标志
_semantic_analyzer = None  # 语义分析器
_func_registry = None  # 原子函数注册表
_attribution_analyzer = None  # 属性推断引擎
_spec_repo = None  # 规范知识库

_engine_thread = threading.Thread(target=_load_engine_sync, daemon=True)  # assignment
_engine_thread.start()  # function call


@asynccontextmanager  # code
async def lifespan(app: FastAPI):  # function call
    """应用生命周期管理

    启动时：等待引擎预热完成（后台线程）
    关闭时：优雅关闭线程池
    """
    # 启动时：等待引擎预热完成
    _engine_thread.join(timeout=120)  # function call
    yield  # 生成
    # 关闭时：清理线程池
    ENGINE_THREAD_POOL.shutdown(wait=False)  # function call


# P64: 增强 OpenAPI 元信息，方便文档生成和 SDK 生成
app = FastAPI(
    title="BAA API",
    version="1.25.0",
    description=(
        "蓝图智能审查引擎（Blueprint AI Agent）— 建筑图纸 DWG/DXF 合规审查。\n"
        "\n"
        "**核心功能：**\n"
        "- `/deconstruct`：图纸解构，提取墙/门/窗/楼梯/消防设备等实体\n"
        "- `/review`：合规审查，按 GB50016/50974/50763/50116 等规范判定\n"
        "- `/review-from-data`：从结构化数据直接审查（跳过图纸解析）\n"
        "- `/batch-review`：批量多文件审查\n"
        "- `/review/compare`：多文件对比审查\n"
        "- `/review/project/summary`：项目级汇总报告\n"
        "- `/api/v1/reverse`：反向重构 DXF 生成\n"
        "- `/thermal/k-value`：热工 K 值反算\n"
        "- `/render`：图纸渲染\n"
        "- `/collab/*`：多用户协作（团队/项目/审批/评论）\n"
        "- `/admin/keys/*`：API 密钥管理\n"
        "\n"
        "**认证：** `Authorization: Bearer ***` 通过 API 密钥验证。"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)  # function call
security = HTTPBearer(auto_error=False)  # function call

# ── 注册子路由模块 ──────────────────────────────────────
from src.api.collab_routes import router as collab_router  # import

app.include_router(collab_router)  # tags 已在 collab_routes 中声明
from src.api.admin_routes import router as admin_router  # import

app.include_router(admin_router)  # tags 已在 admin_routes 中声明
from src.api.review import router as review_router  # import

app.include_router(review_router)  # tags 已在 review/__init__ 中声明

from src.api.render_endpoint import router as render_router  # import

app.include_router(render_router)  # tags 已在 render_endpoint 中声明

from src.api.review.case_routes import router as case_router  # import

app.include_router(case_router, prefix="/api/v1")  # P68 行业案例库

from src.api.model_params_routes import router as model_params_router  # P93

app.include_router(model_params_router, prefix="/api/v1")  # P93 模型参数导出

from .stats_routes import get_stats  # P72 统计仪表盘


@app.get("/api/v1/stats", tags=["API", "API v1"])  # P72
async def api_stats(days: int = Query(30, ge=1, le=365), api_key: str = Depends(verify_api_key)):
    """审查统计仪表盘"""
    return await get_stats(days=days, api_key=api_key)


# ── 静态文件服务 ──────────────────────────────────────────
SPECS_DIR = DATA_DIR / "specs"
if SPECS_DIR.exists():
    app.mount("/data/specs", StaticFiles(directory=str(SPECS_DIR)), name="specs")
if MODELS_DIR.exists():
    app.mount("/models", StaticFiles(directory=str(MODELS_DIR)), name="models")

# ── 挂载前端静态文件 ──────────────────────────────────────
if FRONTEND_DIR.exists():  # condition: FRONTEND_DIR.exists():
    app.mount(
        "/static", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend"
    )  # function call


@app.get("/", tags=["System"])  # function call
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


# get_api_key 已迁移至 api_globals.extract_api_key
# 保留此函数签名仅为兼容旧引用（如有），实际使用 Depends(extract_api_key)
# 通过 verify_api_key 的 Depends 链自动注入
# 注：get_api_key 无实现体，由 extract_api_key 替代


# ── 引擎导入（懒加载） ──────────────────────────────────

# ── 引擎引用（由 _engine_thread 预热加载） ──────────────────────

# 各引擎模块的全局引用，在 _engine_thread 启动前初始化，由 _load_engine_sync 覆盖

# ── 反馈闭环引擎（P10） ────────────────────────────────────
_feedback_manager: Optional[FeedbackManager] = None  # assignment
_learning_engine: Optional[LearningEngine] = None  # 操作


@app.get("/health", tags=["System"])  # function call
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
    parser_ok = _engine_ready  # assignment
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


@app.post("/deconstruct", tags=["Deconstruct"])  # function call
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
    # ── 引擎就绪检查 ────────────────────────────────────────
    if _drawing_parser is None:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "error_code": "ENGINE_NOT_READY",
                "message": "引擎正在预热中，请稍后重试",
            },
        )
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
        except Exception:  # 捕获异常
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

    # Step 3: 规范判定（CPU 密集型，移到线程池避免阻塞事件循环）
    # 250 原子函数 × N 实体的双循环在主事件循环跑会超过 gunicorn 120s timeout
    # 导致 SIGKILL → ERR_EMPTY_RESPONSE。封装为 _do_deconstruct_step3 在线程池中执行
    def _do_deconstruct_step3(
        entities,
    ) -> tuple:  # function: def _do_deconstruct_step3(entities) -> tuple:
        """在线程池中执行规范判定 + 缺失检查 + 统计"""
        from src.baa_engine.spec_repository import SpecRepository

        repo = SpecRepository()
        findings = []
        registry_funcs = _func_registry.list_all()
        total_checks = 0
        seen_violations = set()

        # 遍历处理
        for e in entities:
            for func in registry_funcs:
                total_checks += 1
                threshold_val, unit, op = repo.get_threshold(
                    func.clause_id, building_type, standard
                )
                func.threshold = threshold_val
                func.unit = unit
                func.operator = op
                r = _func_registry.execute_with_timeout(func, e)
                if r is not None and r.result != "PASS":
                    etype = e.get("type", "")
                    dedup_key = (func.clause_id, etype)
                    is_dup = dedup_key in seen_violations
                    if r.result == "FAIL":
                        seen_violations.add(dedup_key)
                    clause = {
                        "standard": "GB50016",
                        "clause_id": func.clause_id,
                        "title": func.name,
                        "text": func.description,
                        "category": func.category.value,
                    }
                    f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])
                    finding_detail = {
                        "finding_id": f.finding_id,
                        "clause_id": func.clause_id,
                        "clause_title": func.name,
                        "description": func.description,
                        "entity_type": etype,
                        "result": r.result,
                        "severity": getattr(r, "severity", "major"),
                        "extracted_value": getattr(r, "extracted_value", getattr(r, "value", 0)),
                        "required_value": threshold_val,
                        "explanation": getattr(
                            f,
                            "explanation",
                            f.description[:100] if hasattr(f, "description") else "",
                        ),
                        "is_duplicate": is_dup,
                    }
                    findings.append(finding_detail)

        # 缺失检查
        for func in registry_funcs:
            if func.category.value != "exist":
                continue
            has_match = any(func.matches(e) for e in entities)
            if not has_match:
                total_checks += 1
                r = _func_registry.execute_with_timeout(func, None)
                if r is not None and r.result != "PASS":
                    dedup_key = (func.clause_id, "missing")
                    is_dup = dedup_key in seen_violations
                    if r.result == "FAIL":
                        seen_violations.add(dedup_key)
                    clause = {
                        "standard": "GB50016",
                        "clause_id": func.clause_id,
                        "title": func.name,
                        "text": func.description,
                        "category": func.category.value,
                    }
                    f = _attribution_analyzer.build_finding(r, clause, {}, entities[:5])
                    finding_detail = {
                        "finding_id": f.finding_id,
                        "clause_id": func.clause_id,
                        "clause_title": func.name,
                        "description": func.description,
                        "entity_type": "missing",
                        "result": r.result,
                        "severity": "critical",
                        "extracted_value": 0,
                        "required_value": 1,
                        "explanation": (f"缺少{func.name}相关实体（{func.description}）"),
                        "is_duplicate": is_dup,
                    }
                    findings.append(finding_detail)

        # 统计
        type_stats = {}
        for e in entities:
            t = e["type"]
            if t not in type_stats:
                type_stats[t] = {"count": 0, "bbox_areas": []}
            type_stats[t]["count"] += 1
            bbox = e["bbox"]
            type_stats[t]["bbox_areas"].append(bbox.get("width", 0) * bbox.get("height", 0))

        elements = []
        for t, stats in sorted(type_stats.items()):
            areas = stats["bbox_areas"]
            total_area = sum(areas) if areas else 0
            elem = {"type": t, "count": stats["count"]}
            if t in ("wall", "corridor", "stair"):
                elem["total_length_m"] = round(total_area**0.5, 1)
            elif t in ("door", "fire_door", "window"):
                elem["total_count"] = stats["count"]
            elif t == "fire_zone":
                elem["total_area_sqm"] = round(total_area, 1)
            elif t in ("equipment", "foundation", "column"):
                elem["total_count"] = stats["count"]
            elif t == "other":
                elem["total_count"] = stats["count"]
            elements.append(elem)

        return findings, registry_funcs, total_checks, elements

    try:
        findings, registry_funcs, total_checks, elements = await loop.run_in_executor(
            ENGINE_THREAD_POOL, _do_deconstruct_step3, entities
        )
    except Exception as e:
        return {
            "status": "error",
            "error_code": "REVIEW_FAILED",
            "message": f"规范判定失败: {e}",
            "file_id": file_id,
        }

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

    result = {  # 操作
        "status": "success",  # 字段
        "elements": elements,  # 实体类型统计
        "entities": entities,  # 所有解析出的实体（供 review-from-data 使用）
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
    xref_warning = result.get("warning") or result.get("xref_warning")  # 安全获取值
    if xref_warning:  # condition: xref_warning
        result["xref_warning"] = xref_warning  # assignment

    # 根据条件判断分支：if use_yolo
    if use_yolo:  # condition: use_yolo:
        result["yolo_entities"] = len(yolo_entities)  # 操作
        result["yolo_enabled"] = True  # 操作

    return _sanitize_for_json(result)  # 操作


@app.post("/review", tags=["Review"])  # function call
@app.get("/api/v1/functions", tags=["API", "API v1"])
async def list_functions(api_key: str = Depends(verify_api_key)):
    """获取原子函数库列表（含简介、参数、模型）"""
    funcs = []
    for f in _func_registry.list_all():
        funcs.append(
            {
                "func_id": f.func_id,
                "name": f.name,
                "description": f.description,
                "category": f.category.value if hasattr(f.category, "value") else str(f.category),
                "clause_id": f.clause_id,
                "target_entities": list(f.target_entities),
                "operator": f.operator,
                "threshold": f.threshold,
                "unit": f.unit,
                "depends_on": f.depends_on,
            }
        )
    return {"status": "ok", "count": len(funcs), "functions": funcs}


@app.get("/api/v1/specs", tags=["API", "API v1"])
async def list_specs(api_key: str = Depends(verify_api_key)):
    """获取规范库列表（含所有条款）"""
    specs = []
    for c in _spec_repo.list_all():
        specs.append(
            {
                "clause_id": c.clause_id,
                "standard": c.standard,
                "title": c.title,
                "text": c.text,
                "level": c.level,
                "func_id": c.func_id,
                "category": c.category,
                "params": c.params,
            }
        )
    return {"status": "ok", "count": len(specs), "specs": specs}


# ═══════════════════════════════════════════════════════════════
# P66: 规范版本管理 — 版本列表 + 版本对比
# ═══════════════════════════════════════════════════════════════


@app.get("/api/v1/specs/versions", tags=["API", "API v1"])
async def list_spec_versions(
    standard: str = None,
    api_key: str = Depends(verify_api_key),
):
    """获取支持的所有规范版本列表

    Args:
        standard: 指定标准名称（如 GB 50016），None 返回全部标准
    """
    from src.baa_engine.spec_data.versioning import VersionManager

    mgr = VersionManager()
    if standard:
        versions = mgr.list_versions(standard)
        return {"status": "ok", "standard": standard, "versions": versions}
    return {"status": "ok", "versions": mgr.list_versions()}


@app.get(
    "/api/v1/specs/compare",
    tags=["API", "API v1"],
)
async def compare_spec_versions(
    standard: str,
    old_version: str,
    new_version: str = None,
    api_key: str = Depends(verify_api_key),
):
    """对比两个版本间的规范差异

    Args:
        standard: 标准名称（如 GB 50016）
        old_version: 旧版本（如 2014）
        new_version: 新版本（如 2025）；None 表示从 old_version 到最新版
    """
    from src.baa_engine.spec_data.versioning import VersionManager

    mgr = VersionManager()
    return mgr.compare_versions(standard, old_version, new_version)


@app.get(
    "/api/v1/specs/change-log",
    tags=["API", "API v1"],
)
async def get_change_log(
    standard: str,
    old_version: str,
    new_version: str = None,
    api_key: str = Depends(verify_api_key),
):
    """获取版本变更日志（详细条目）"""
    from src.baa_engine.spec_data.versioning import VersionManager

    mgr = VersionManager()
    return mgr.get_change_log(standard, old_version, new_version)


@app.post("/api/v1/functions/{func_id}/update", tags=["API", "API v1"])
async def update_function(func_id: str, body: dict, api_key: str = Depends(verify_api_key)):
    """更新原子函数的阈值/运算符等参数"""
    f = _func_registry.get(func_id)
    if not f:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "error_code": "FUNC_NOT_FOUND",
                "message": f"函数 {func_id} 不存在",
            },
        )
    for key in ["threshold", "operator", "name", "description", "unit"]:
        if key in body:
            setattr(f, key, body[key])
    return {"status": "ok", "message": f"{func_id} 已更新"}


@app.post("/api/v1/reverse", tags=["API", "API v1"])
async def reverse_generate(body: dict, api_key: str = Depends(verify_api_key)):
    """反向重构：根据房间规格生成合规 DXF"""
    from src.baa_engine.reverse_engine import ReverseEngine, RoomSpec, RoomType, validate_roundtrip
    import tempfile  # import
    from pathlib import Path  # path utils
    import os  # stdlib: filesystem ops

    spec = RoomSpec(
        room_type=RoomType(body.get("room_type", "office")),
        width_mm=body.get("width_mm", 5000),
        height_mm=body.get("height_mm", 4000),
        door_width_mm=body.get("door_width_mm"),
    )
    engine = ReverseEngine()
    constraints = engine.infer_constraints(spec)

    tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    tmp.close()
    engine.generate_dxf(spec, tmp.name)

    with open(tmp.name, "r") as f:
        dxf_content = f.read()

    # 验证闭环
    v = validate_roundtrip(Path(tmp.name))
    os.unlink(tmp.name)

    return {
        "status": "ok",
        "spec": {
            "room_type": spec.room_type.value,
            "width_mm": spec.width_mm,
            "height_mm": spec.height_mm,
            "door_width_mm": spec.door_width_mm,
        },
        "constraints": {
            "min_width_mm": constraints.min_width_mm,
            "min_height_mm": constraints.min_height_mm,
            "min_door_width_mm": constraints.min_door_width_mm,
            "min_area_m2": constraints.min_area_m2,
            "notes": constraints.notes,
        },
        "dxf": dxf_content,
        "validation": {
            "all_pass": v.get("all_pass", False),
            "fail_count": v.get("fail_count", 0),
            "entities": v.get("entities", {}),
        },
    }


@app.post("/api/v1/reverse/multi", tags=["API", "API v1"])
async def reverse_generate_multi(body: dict, api_key: str = Depends(verify_api_key)):
    """多房间布局生成"""
    from src.baa_engine.reverse_engine import (
        MultiRoomEngine,
        RoomSpec,
        RoomType,
        validate_roundtrip,
    )
    import tempfile  # import
    from pathlib import Path  # path utils
    import os  # stdlib: filesystem ops

    # body: { rooms: [{room_type, width_mm, height_mm, door_width_mm}...] }
    specs = [
        RoomSpec(
            room_type=RoomType(r.get("room_type", "office")),
            width_mm=r.get("width_mm", 5000),
            height_mm=r.get("height_mm", 4000),
            door_width_mm=r.get("door_width_mm"),
        )
        for r in body.get("rooms", [])
    ]

    if not specs:
        return {"status": "error", "message": "rooms 列表为空"}

    multi = MultiRoomEngine()
    layout = multi.generate_layout(specs)

    tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    tmp.close()
    multi.build_dxf(layout, tmp.name)

    with open(tmp.name, "r") as f:
        dxf_content = f.read()

    # 验证闭环
    validation = None
    if body.get("validate", False):
        v = validate_roundtrip(Path(tmp.name))
        validation = {
            "all_pass": v.get("all_pass", False),
            "fail_count": v.get("fail_count", 0),
            "entities": v.get("entities", {}),
        }

    os.unlink(tmp.name)

    return {
        "status": "ok",
        "dxf": dxf_content,
        "layout": {
            "rooms": [
                {
                    "type": r.room_type.value,
                    "x": r.x_mm,
                    "y": r.y_mm,
                    "w": r.width_mm,
                    "h": r.height_mm,
                }
                for r in layout.rooms
            ],
            "corridor": (
                {"w": layout.corridor.width_mm, "h": layout.corridor.height_mm}
                if layout.corridor
                else None
            ),
        },
        "validation": validation,
    }


@app.post("/api/v1/reverse/export-dwg", tags=["API", "API v1"])
async def reverse_export_dwg(
    dxf_content: str,
    filename: str = None,
    api_key: str = Depends(verify_api_key),
):
    """P67: 将反向重构生成的 DXF 内容导出为 DWG 文件。

    请求体: {"dxf_content": "<DXF文本>", "filename": "output.dwg"}
    返回: HTTP下载（DWG 或 DXF 降级）
    """
    from src.baa_engine.reverse_engine import ReverseEngine
    import tempfile
    import os

    engine = ReverseEngine()

    # 写入临时 DXF
    tmp_dxf = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    tmp_dxf.close()
    with open(tmp_dxf.name, "w") as f:
        f.write(dxf_content)

    # 输出路径
    fname = filename or "output.dwg"
    tmp_dwg = tempfile.NamedTemporaryFile(
        suffix=".dwg" if fname.endswith(".dwg") else ".dxf",
        delete=False,
    )
    tmp_dwg.close()
    out_path = tmp_dwg.name
    # 如果请求的是 dwg，尝试导出；否则直接返回 dxf
    if fname.endswith(".dwg"):
        out_path = engine.export_dwg(tmp_dxf.name, tmp_dwg.name)

    os.unlink(tmp_dxf.name)

    # 返回文件下载
    import mimetypes

    mime, _ = mimetypes.guess_type(out_path) or ("application/octet-stream", None)
    from fastapi.responses import FileResponse

    # 使用正确的原始文件名
    return FileResponse(out_path, media_type=mime, filename=fname)


# ═══════════════════════════════════════════════════════════════
# P41: AI 辅助修正建议（LLM 驱动）
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/correction/suggestions", tags=["API", "API v1"])
async def generate_correction_suggestions(
    body: dict,
    api_key: str = Depends(verify_api_key),
):
    """基于审查违规结果生成修正建议（rule/llm/hybrid 三种模式）

    请求体：
    {
        "review_id": "<可选，审查会话 ID>",
        "findings": [  # 审查违规结果列表
            {"entity_id": "e1", "func_id": "DIM-001", ...},
            ...
        ],
        "entities": [  # 实体信息（可选）
            {"id": "e1", "type": "stair", "properties": {...}},
            ...
        ],
        "mode": "rule|llm|hybrid",  # 模式
    }
    """
    import os

    from src.baa_engine.llm_correction import LLMCorrectionEngine

    findings = body.get("findings", [])
    entities = body.get("entities", [])
    mode = body.get("mode", os.environ.get("BAA_CORRECTION_MODE", "hybrid"))

    engine = LLMCorrectionEngine()
    suggestions = engine.generate(findings, entities, mode=mode)

    return {
        "status": "ok",
        "mode": engine.mode,
        "count": len(suggestions),
        "suggestions": [
            {
                "entity_id": s.entity_id,
                "entity_type": s.entity_type,
                "clause_id": s.clause_id,
                "clause_title": s.clause_title,
                "action": s.action,
                "description": s.description,
                "current_value": s.current_value,
                "required_value": s.required_value,
                "delta": s.delta,
                "recommendation": s.recommendation,
                "source": s.source,
            }
            for s in suggestions
        ],
    }


# ═══════════════════════════════════════════════════════════════
# P48: 施工图审查深度标准
# ═══════════════════════════════════════════════════════════════


@app.get("/api/v1/construction-review", tags=["API", "API v1"])
async def list_construction_review_items(
    major: str = None,
    level: str = None,
    category: str = None,
    method: str = None,
    api_key: str = Depends(verify_api_key),
):
    """P48: 施工图审查深度标准列表。

    过滤参数:
    - major: 专业 (arch/struct/mech/elec/plumb)
    - level: 深度等级 (L1/L2/L3)
    - category: 类别 (completeness/annotation/coordination)
    - method: 检查方式 (auto/manual/ai)
    """
    from src.baa_engine.spec_data import get_construction_review_items

    items = get_construction_review_items(
        major=major,
        level=level,
        category=category,
        check_method=method,
    )
    return {
        "status": "ok",
        "items": items,
        "total": len(items),
        "summary": {
            "total": len(items),
            "L1": len([i for i in items if i["level"] == "L1"]),
            "L2": len([i for i in items if i["level"] == "L2"]),
            "L3": len([i for i in items if i["level"] == "L3"]),
            "auto_checkable": len([i for i in items if i["check_method"] == "auto"]),
            "manual_check": len([i for i in items if i["check_method"] == "manual"]),
            "by_major": {
                m: len([i for i in items if i["major"] == m])
                for m in ["arch", "struct", "mech", "elec", "plumb"]
            },
        },
    }


@app.post("/api/v1/construction-review/report", tags=["API", "API v1"])
async def generate_construction_review_report(
    body: dict,
    api_key: str = Depends(verify_api_key),
):
    """P48: 生成施工图审查深度评分报告。

    请求体: {"file_id": "xxx"}
    返回: 各 CD 项达标状态 + 总体得分
    """
    from src.baa_engine.spec_data import get_construction_review_items

    file_id = body.get("file_id")
    if not file_id:
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": "file_id 必填"},
        )

    # 自动检查项
    auto_items = get_construction_review_items(check_method="auto")
    auto_result = [
        {
            "item_id": i["item_id"],
            "title": i["title"],
            "level": i["level"],
            "check_method": i["check_method"],
            "status": "PASS" if i["func_id"] else "PENDING",
            "score": 100.0 if i["func_id"] else 0.0,
        }
        for i in auto_items
    ]

    # 人工检查项（全部标记为待检查）
    manual_items = get_construction_review_items(check_method="manual")
    manual_result = [
        {
            "item_id": i["item_id"],
            "title": i["title"],
            "level": i["level"],
            "check_method": i["check_method"],
            "status": "PENDING",
            "score": 0.0,
        }
        for i in manual_items
    ]

    all_items = auto_result + manual_result
    scored = [i for i in all_items if i["status"] == "PASS"]
    total = len(all_items)
    score = round(sum(i["score"] for i in scored) / max(total, 1) * 100, 1)

    return {
        "status": "ok",
        "file_id": file_id,
        "total_items": total,
        "passed": len(scored),
        "pending": total - len(scored),
        "score": score,
        "grade": "A" if score >= 80 else ("B" if score >= 60 else "C"),
        "items": all_items,
    }
