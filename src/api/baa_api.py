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


app = FastAPI(title="BAA API", version="1.0.0", lifespan=lifespan)  # function call
security = HTTPBearer(auto_error=False)  # function call

# ── 注册子路由模块 ──────────────────────────────────────
from src.api.collab_routes import router as collab_router  # import

app.include_router(collab_router)  # function call
from src.api.admin_routes import router as admin_router  # import

app.include_router(admin_router)  # function call
from src.api.review_routes import router as review_router  # import

app.include_router(review_router)  # function call

from src.api.render_endpoint import router as render_router  # import

app.include_router(render_router)  # function call

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
    xref_warning = result.get("warning") or result.get("xref_warning")  # 安全获取值
    if xref_warning:  # condition: xref_warning
        result["xref_warning"] = xref_warning  # assignment

    # 根据条件判断分支：if use_yolo
    if use_yolo:  # condition: use_yolo:
        result["yolo_entities"] = len(yolo_entities)  # 操作
        result["yolo_enabled"] = True  # 操作

    return result  # return


@app.post("/review")  # function call
@app.get("/api/v1/functions")
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


@app.post("/api/v1/functions/{func_id}/update")
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


@app.post("/api/v1/reverse")
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


@app.post("/api/v1/reverse/multi")
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


# ═══════════════════════════════════════════════════════════════
# P41: AI 辅助修正建议（LLM 驱动）
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/correction/suggestions")
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
