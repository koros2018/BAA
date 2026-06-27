"""
BAA API 服务层 - FastAPI 实现
端点: /deconstruct, /reconstruct, /order/{id}, /health
"""
import uuid
import os
import time
import json
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timedelta

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Security, Query, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


# ── 配置 ──────────────────────────────────────────────────

# ── 项目工作路径（默认：项目根目录下的 data/） ───────────

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

SUPPORTED_FORMATS = {"dxf", "dwg"}
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

# API Key（从环境变量加载）
API_KEYS = set()
_api_key = os.getenv("BAA_API_KEY", "")
if _api_key:
    API_KEYS.add(_api_key)

# 共享密钥（用于 auth_token 验证，支持多密钥宽限期）
# 格式：逗号分隔，第一个为最新密钥，后续为旧密钥（48h宽限期）
AUTH_SECRETS = [s.strip() for s in os.getenv("BAA_AUTH_SECRET", "").split(",") if s.strip()]
if not AUTH_SECRETS:
    # 开发模式默认密钥
    AUTH_SECRETS = ["baa-dev-secret-change-in-production"]


# ── 线程池（CPU密集型引擎任务用） ─────────────────────────
import asyncio
from concurrent.futures import ThreadPoolExecutor
ENGINE_THREAD_POOL = ThreadPoolExecutor(
    max_workers=min(8, (os.cpu_count() or 4) * 2),
    thread_name_prefix="baa-engine"
)


# ── 授权验证 ──────────────────────────────────────────────

import hmac
import hashlib
import base64


# ── API密钥管理 ──────────────────────────────────────────

from src.baa_engine.api_key_manager import get_key_manager, ApiKeyPermission


def generate_auth_token(payload: dict, secret: str = None) -> str:
    """生成 auth_token（JWT格式，HMAC-SHA256）
    默认使用最新密钥
    """
    if secret is None:
        secret = AUTH_SECRETS[0]  # 最新密钥
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(
        json.dumps(header, separators=(",", ":")).encode()).rstrip(b"=").decode()
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=").decode()
    signing_input = f"{header_b64}.{payload_b64}"
    sig = hmac.new(
        secret.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_auth_token(token: str) -> Optional[dict]:
    """验证 auth_token，使用所有活跃密钥（支持宽限期）"""
    for secret in AUTH_SECRETS:
        result = _verify_with_secret(token, secret)
        if result is not None:
            return result
    return None


def _verify_with_secret(token: str, secret: str) -> Optional[dict]:
    """用单个密钥验证"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"

        def add_padding(s):
            return s + "=" * (4 - len(s) % 4)

        expected_sig = hmac.new(
            secret.encode(), signing_input.encode(), hashlib.sha256
        ).digest()

        actual_sig = base64.urlsafe_b64decode(add_padding(sig_b64))
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload = json.loads(base64.urlsafe_b64decode(add_padding(payload_b64)))

        # 验证有效期（兼容带时区和不带时区的时间字符串）
        expires = payload.get("expires_at")
        if expires:
            from datetime import timezone
            exp_time = datetime.fromisoformat(expires)
            if exp_time.tzinfo is None:
                exp_time = exp_time.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp_time:
                return None

        return payload
    except Exception:
        return None


# ── FastAPI 应用 ──────────────────────────────────────────

# 前端静态文件路径
FRONTEND_DIR = PROJECT_ROOT / "src" / "frontend"


# ── 引擎预热（app启动时加载） ──────────────────────────────

def _load_engine():
    """预热加载引擎模块，每个 worker 启动时执行一次"""
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.semantic_analyzer import SemanticAnalyzer
    from src.baa_engine.atomic_functions import FuncRegistry
    from src.baa_engine.attribution_analyzer import AttributionAnalyzer
    from src.baa_engine.spec_repository import SpecRepository
    global _drawing_parser, _semantic_analyzer, _func_registry, _attribution_analyzer, _spec_repo
    _drawing_parser = DrawingParser()
    _semantic_analyzer = SemanticAnalyzer()
    _func_registry = FuncRegistry()
    _attribution_analyzer = AttributionAnalyzer()
    _spec_repo = SpecRepository()
    print(f"[BAA] 引擎已预热: {_func_registry.count}个原子函数, {_spec_repo.count}条规范")


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时：预热引擎
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(ENGINE_THREAD_POOL, _load_engine)
    yield
    # 关闭时：清理线程池
    ENGINE_THREAD_POOL.shutdown(wait=False)


app = FastAPI(title="BAA API", version="1.0.0", lifespan=lifespan)
security = HTTPBearer(auto_error=False)

# 挂载前端静态文件
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


@app.get("/")
async def root():
    """返回前端 UI 页面"""
    from fastapi.responses import HTMLResponse
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
        return HTMLResponse(content=content, status_code=200)
    # 降级：返回 JSON 信息
    return {
        "service": "BAA - Building Audit Assistant",
        "version": "1.0.0",
        "api_docs": "/docs",
        "endpoints": {
            "/health": "服务健康检查",
            "/deconstruct": "图纸解析与违规范判定",
            "/review": "图纸合规审查（详细报告）",
            "/reconstruct": "图纸重构",
            "/order/{order_id}": "查询订单/任务状态",
        },
        "note": "前端 UI 文件未找到，请检查 src/frontend/index.html"
    }

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_api_key(authorization: str = Query("", description="Bearer API Key")):
    """获取 API Key（Query参数或Header）"""
def verify_api_key(request: Request):
    """验证 API Key（使用ApiKeyManager）"""
    if not API_KEYS:
        return "anonymous"
    auth_header = request.headers.get("authorization", "")
    
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        return "anonymous"  # 开发模式：没传key也放行
    
    # 使用ApiKeyManager验证
    km = get_key_manager()
    key_info = km.validate_key(token)
    if key_info:
        km.record_usage(token)
        return token
    
    if token in API_KEYS:
        return token
    
    # 开发模式：没传有效key也放行
    return "anonymous"


def require_admin(request: Request, api_key: str = ""):
    """验证admin权限（用于admin端点）
    开发模式（API_KEYS 为空）时不校验，直接放行。
    """
    if not API_KEYS:
        return "anonymous"
    km = get_key_manager()
    key_info = km.validate_key(api_key)
    if key_info and key_info.get("permission") == "admin":
        return api_key
    # 环境变量key也视为admin
    if api_key and api_key in API_KEYS:
        return api_key
    raise HTTPException(status_code=403, detail={
        "status": "error", "error_code": "FORBIDDEN",
        "message": "需要admin权限"
    })


# ── 文件管理 ──────────────────────────────────────────────

def generate_file_id() -> str:
    return f"baa-file-{uuid.uuid4().hex[:12]}"


def store_file(content: bytes, file_id: str, extension: str) -> Path:
    path = FILES_DIR / f"{file_id}.{extension}"
    path.write_bytes(content)
    return path


def get_file_path(file_id: str) -> Optional[Path]:
    for ext in SUPPORTED_FORMATS:
        path = FILES_DIR / f"{file_id}.{ext}"
        if path.exists():
            return path
    return None


# ── 引擎导入（懒加载） ──────────────────────────────────

# ── 引擎引用（由 lifespan 预热加载） ──────────────────────

_drawing_parser = None
_semantic_analyzer = None
_func_registry = None
_attribution_analyzer = None
_spec_repo = None


@app.get("/health")
async def health():
    """增强型健康检查（含子系统状态）"""
    engine_ok = _func_registry is not None
    spec_ok = _spec_repo is not None
    parser_ok = _drawing_parser is not None
    yolo_ok = False
    yolo_info = "未加载"
    try:
        from src.baa_engine.yolo_integrator import get_yolo_model
        yolo_model = get_yolo_model()
        if yolo_model is not None:
            yolo_ok = True
            yolo_info = "就绪"
    except Exception:
        yolo_info = "不可用"
    
    all_ok = engine_ok and spec_ok and parser_ok
    return {
        "status": "ok" if all_ok else "degraded",
        "version": "1.10.0",
        "uptime_seconds": int(time.time() - _start_time) if hasattr(health, "_start_time") else 0,
        "engine_status": "ready" if all_ok else "degraded",
        "supported_formats": list(SUPPORTED_FORMATS),
        "api_version": "v1",
        "subsystems": {
            "engine": {"status": "ok" if engine_ok else "down"},
            "spec_repository": {"status": "ok" if spec_ok else "down"},
            "drawing_parser": {"status": "ok" if parser_ok else "down"},
            "yolo_integrator": {"status": "ok" if yolo_ok else "unavailable", "info": yolo_info},
        },
        "data_dir": str(DATA_DIR),
    }

# 记录启动时间
_start_time = time.time()


@app.post("/deconstruct")
async def deconstruct(
    file: UploadFile = File(...),
    building_type: str = Query("civil", description="建筑类型: civil(民用) / industrial(工业)"),
    use_yolo: bool = Query(False, description="是否使用 YOLO 图元检测增强"),
    request: Request = None,
    api_key: str = Depends(verify_api_key),
):
    """图纸解构（免费）"""
    # 检查文件格式
    filename = file.filename or "unknown"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "UNSUPPORTED_FORMAT",
                "message": f"不支持的文件格式: {ext}。支持: {', '.join(SUPPORTED_FORMATS)}",
            }
        )

    # 检查文件大小
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "FILE_TOO_LARGE",
                "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",
            }
        )

    # 存储文件
    file_id = generate_file_id()
    file_path = store_file(content, file_id, ext)

    # 调用核心引擎进行解析
    start = time.time()
    loop = asyncio.get_event_loop()

    # Step 1: 图纸解析（CPU密集型 → 线程池）
    result = await loop.run_in_executor(
        ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id
    )
    if not result.success:
        return {
            "status": "error",
            "error_code": "PARSE_FAILED",
            "message": f"图纸解析失败: {result.error}",
            "file_id": file_id,
        }

    # Step 2: 语义分析（CPU密集型 → 线程池）
    semantic = await loop.run_in_executor(
        ENGINE_THREAD_POOL,
        lambda: _semantic_analyzer.analyze(
            result.primitives, result.dimensions,
            building_type=building_type
        )
    )
    entities = semantic["entities"]
    relations = semantic["relations"]

    # Step 2.5: YOLO 图元检测增强（可选）
    yolo_entities = []
    if use_yolo:
        try:
            from src.baa_engine.yolo_integrator import YOLODetectionIntegrator
            yolo = YOLODetectionIntegrator()
            if yolo.load_model():
                _, dets = yolo.render_and_predict(str(file_path))
                yolo_entities = yolo.detections_to_entities(dets)
                # 合并到实体列表（去重，优先保留规则解析结果）
                existing_types = set(e.get("type", "") for e in entities)
                for ye in yolo_entities:
                    if ye["type"] not in existing_types:
                        entities.append(ye)
        except Exception as yolo_e:
            # YOLO 失败不影响主流程
            pass

    # Step 2.75: DIMENSION 尺寸标注注入（自动反推实体属性）
    try:
        from src.baa_engine.dimension_parser import DimensionParser
        dp = DimensionParser()
        dims = dp.extract_dimensions(str(file_path))
        if dims:
            entities = dp.inject_into_entities(dims, entities)
    except Exception:
        pass

    # Step 3: 规范判定（使用 building_type 确定阈值，含去重）
    from src.baa_engine.spec_repository import SpecRepository
    repo = SpecRepository()
    findings = []
    registry_funcs = _func_registry.list_all()
    total_checks = 0
    seen_violations = set()  # (clause_id, entity_type) 去重

    for e in entities:
        for func in registry_funcs:
            total_checks += 1
            threshold_val, unit, op = repo.get_threshold(func.clause_id, building_type)
            func.threshold = threshold_val
            func.unit = unit
            func.operator = op
            r = func.execute(e)
            if r is not None and r.result != "PASS":
                # 去重：同一clause_id+同一entity_type只记一次FAIL
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
                # 详细违规输出
                finding_detail = {
                    "finding_id": f.finding_id,
                    "clause_id": func.clause_id,
                    "clause_title": func.name,
                    "description": func.description,
                    "entity_type": etype,
                    "result": r.result,
                    "severity": getattr(r, 'severity', 'major'),
                    "extracted_value": getattr(r, 'extracted_value', getattr(r, 'value', 0)),
                    "required_value": threshold_val,
                    "explanation": getattr(f, 'explanation', f.description[:100] if hasattr(f, 'description') else ''),
                    "is_duplicate": is_dup,
                }
                findings.append(finding_detail)

    # 缺失检查：对 EXIST-* 函数检查是否有匹配实体
    for func in registry_funcs:
        if func.category.value != "exist":
            continue
        has_match = any(func.matches(e) for e in entities)
        if not has_match:
            total_checks += 1
            r = func.execute(None)
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
                    "severity": 'critical',
                    "extracted_value": 0,
                    "required_value": 1,
                    "explanation": f"缺少{func.name}相关实体（{func.description}）",
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
            elem["total_length_m"] = round(total_area ** 0.5, 1)
        elif t in ("door", "fire_door", "window"):
            elem["total_count"] = stats["count"]
        elif t == "fire_zone":
            elem["total_area_sqm"] = round(total_area, 1)
        elements.append(elem)

    elapsed = int((time.time() - start) * 1000)

    # 统计违规严重度分布
    fail_count = len([f for f in findings if f["result"] == "FAIL" and not f["is_duplicate"]])
    warn_count = len([f for f in findings if f["result"] == "WARN" and not f["is_duplicate"]])
    critical_count = len([f for f in findings if f.get("severity") == "critical" and not f["is_duplicate"]])

    result = {
        "status": "success",
        "elements": elements,
        "relations": len(relations),
        "findings": findings,  # 完整违规详情（含去重标记）
        "total_checks": total_checks,
        "summary": {
            "total_violations": fail_count,
            "warnings": warn_count,
            "critical": critical_count,
            "total_checks": total_checks,
        },
        "confidence": 0.85 if len(entities) > 0 else 0,
        "file_id": file_id,
        "building_type": building_type,
        "processing_time_ms": elapsed,
    }

    if use_yolo:
        result["yolo_entities"] = len(yolo_entities)
        result["yolo_enabled"] = True

    return result


@app.post("/review")
async def review(
    file: UploadFile = File(...),
    full: bool = Query(False, description="返回完整图元列表"),
    building_type: str = Query("civil", description="建筑类型: civil(民用) / industrial(工业)"),
    request: Request = None,
    api_key: str = Depends(verify_api_key),
):
    """图纸合规审查（免费试用）"""
    filename = file.filename or "unknown"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "UNSUPPORTED_FORMAT",
                "message": f"不支持的文件格式: {ext}",
            }
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "FILE_TOO_LARGE",
                "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",
            }
        )

    file_id = generate_file_id()
    file_path = store_file(content, file_id, ext)

    start = time.time()
    loop = asyncio.get_event_loop()

    # 解析（CPU密集型 → 线程池）
    result = await loop.run_in_executor(
        ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id
    )
    if not result.success:
        return {
            "status": "error",
            "error_code": "PARSE_FAILED",
            "message": f"图纸解析失败: {result.error}",
            "file_id": file_id,
        }

    # 语义分析（采样1000限制 → 线程池）
    semantic = await loop.run_in_executor(
        ENGINE_THREAD_POOL,
        lambda: _semantic_analyzer.analyze(
            result.primitives, result.dimensions,
            building_type=building_type
        )
    )
    entities = semantic["entities"]

    # 规范判定（使用 building_type 确定阈值）
    from src.baa_engine.spec_repository import SpecRepository
    repo = SpecRepository()
    from collections import Counter
    clause_results = Counter()
    details = []
    registry_funcs = _func_registry.list_all()

    # 收集已出现的实体类型
    found_entity_types = set(e["type"] for e in entities)

    for e in entities:
        for func in registry_funcs:
            # 根据 building_type 获取实际阈值
            threshold_val, unit, op = repo.get_threshold(func.clause_id, building_type)
            func.threshold = threshold_val
            func.unit = unit
            func.operator = op
            r = func.execute(e)
            if r is None:
                continue
            clause_results[func.clause_id] += 1
            if r.result != "PASS":
                clause = {
                    "standard": "GB50016",
                    "clause_id": func.clause_id,
                    "title": func.name,
                    "text": func.description,
                    "category": func.category.value,
                }
                f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])
                details.append({
                    "entity_id": e.get("id", e.get("type", "")),
                    "entity_type": e["type"],
                    "clause_id": f.clause.get("clause_id", ""),
                    "clause_title": f.clause.get("title", ""),
                    "result": f.judgement["result"],
                    "extracted_value": f.extracted_params["extracted_value"],
                    "required_value": f.extracted_params.get("required_value", 1.2),
                    "difference": f.extracted_params.get("difference", 0),
                    "explanation": f.explanation[:120],
                })

    # 缺失检查：对 EXIST-* 函数检查是否有匹配实体
    for func in registry_funcs:
        if func.category.value != "exist":
            continue
        has_match = any(func.matches(e) for e in entities)
        if not has_match:
            r = func.execute(None)  # 触发缺失检查模式
            if r is not None and r.result != "PASS":
                clause = {
                    "standard": "GB50016",
                    "clause_id": func.clause_id,
                    "title": func.name,
                    "text": func.description,
                    "category": func.category.value,
                }
                f = _attribution_analyzer.build_finding(r, clause, {}, entities[:5])
                details.append({
                    "entity_id": "",
                    "entity_type": "missing",
                    "clause_id": f.clause.get("clause_id", ""),
                    "clause_title": f.clause.get("title", ""),
                    "result": f.judgement["result"],
                    "extracted_value": 0.0,
                    "required_value": f.extracted_params.get("required_value", 1.0),
                    "difference": -f.extracted_params.get("required_value", 1.0),
                    "explanation": f.explanation[:120],
                })

    elapsed = int((time.time() - start) * 1000)

    # 统计
    entity_types = Counter(e["type"] for e in entities)
    violation_count = Counter(d["clause_id"] for d in details)

    response_data = {
        "status": "success",
        "summary": {
            "total_entities": len(entities),
            "entity_types": dict(entity_types),
            "total_checks": len(entities) * len(registry_funcs),
            "violations": len(details),
            "violation_by_clause": dict(violation_count.most_common(10)),
        },
        "details": details[:100],  # 最多返回100条
        "file_id": file_id,
        "building_type": building_type,
        "processing_time_ms": elapsed,
    }

    # 生成修正建议
    try:
        from src.baa_engine.correction_engine import CorrectionEngine
        correction_engine = CorrectionEngine()
        review_result_for_correction = {
            "findings": [{
                "entity_id": d["entity_id"],
                "entity_type": d["entity_type"],
                "clause_id": d["clause_id"],
                "clause_title": d["clause_title"],
                "extracted_value": d["extracted_value"],
                "required_value": d["required_value"],
                "difference": d["difference"],
            } for d in details]
        }
        corrections = correction_engine.generate_for_result(review_result_for_correction)
        response_data["corrections"] = corrections
    except Exception as e:
        response_data["corrections"] = []

    if full:
        response_data["all_entities"] = [
            {"id": e.get("id", e.get("type", "")), "type": e["type"], "bbox": e["bbox"]}
            for e in entities
        ]

    return response_data


@app.post("/batch-review")
async def batch_review(
    files: List[UploadFile] = File(...),
    building_type: str = Query("civil", description="建筑类型: civil(民用) / industrial(工业)"),
    api_key: str = Depends(verify_api_key),
):
    """多文件批量审查
    
    同时审查多个图纸文件，返回汇总报告和交叉分析。
    """
    if len(files) < 1:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "请至少上传一个文件"})
    if len(files) > 20:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "单次最多审查20个文件"})

    start = time.time()
    loop = asyncio.get_event_loop()
    from src.baa_engine.spec_repository import SpecRepository
    from collections import Counter
    repo = SpecRepository()
    registry_funcs = _func_registry.list_all()

    results = []
    all_details = []
    all_entities = []
    total_violations = 0
    total_checks = 0

    for file in files:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in SUPPORTED_FORMATS:
            results.append({
                "filename": file.filename,
                "status": "error",
                "error_code": "UNSUPPORTED_FORMAT",
                "message": f"不支持的文件格式: {ext}",
            })
            continue

        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            results.append({
                "filename": file.filename,
                "status": "error",
                "error_code": "FILE_TOO_LARGE",
                "message": f"文件过大（{len(content)/1024/1024:.1f}MB），最大{MAX_FILE_SIZE_MB}MB",
            })
            continue

        file_id = generate_file_id()
        file_path = store_file(content, file_id, ext)

        # 解析
        result = await loop.run_in_executor(
            ENGINE_THREAD_POOL, _drawing_parser.parse, str(file_path), file_id
        )
        if not result.success:
            results.append({
                "filename": file.filename,
                "status": "error",
                "error_code": "PARSE_FAILED",
                "message": f"图纸解析失败: {result.error}",
            })
            continue

        # 语义分析
        semantic = await loop.run_in_executor(
            ENGINE_THREAD_POOL,
            lambda: _semantic_analyzer.analyze(
                result.primitives, result.dimensions,
                building_type=building_type
            )
        )
        entities = semantic["entities"]

        # 规范判定
        details = []
        found_entity_types = set(e["type"] for e in entities)

        for e in entities:
            for func in registry_funcs:
                threshold_val, unit, op = repo.get_threshold(func.clause_id, building_type)
                func.threshold = threshold_val
                func.unit = unit
                func.operator = op
                r = func.execute(e)
                if r is None:
                    continue
                if r.result != "PASS":
                    clause = {
                        "standard": "GB50016",
                        "clause_id": func.clause_id,
                        "title": func.name,
                        "text": func.description,
                        "category": func.category.value,
                    }
                    f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])
                    details.append({
                        "entity_id": e.get("id", e.get("type", "")),
                        "entity_type": e["type"],
                        "clause_id": f.clause.get("clause_id", ""),
                        "clause_title": f.clause.get("title", ""),
                        "result": f.judgement["result"],
                        "extracted_value": f.extracted_params["extracted_value"],
                        "required_value": f.extracted_params.get("required_value", 1.2),
                        "difference": f.extracted_params.get("difference", 0),
                        "explanation": f.explanation[:120],
                    })

        # 缺失检查
        for func in registry_funcs:
            if func.category.value != "exist":
                continue
            has_match = any(func.matches(e) for e in entities)
            if not has_match:
                r = func.execute(None)
                if r is not None and r.result != "PASS":
                    clause = {
                        "standard": "GB50016",
                        "clause_id": func.clause_id,
                        "title": func.name,
                        "text": func.description,
                        "category": func.category.value,
                    }
                    f = _attribution_analyzer.build_finding(r, clause, {}, entities[:5])
                    details.append({
                        "entity_id": "",
                        "entity_type": "missing",
                        "clause_id": f.clause.get("clause_id", ""),
                        "clause_title": f.clause.get("title", ""),
                        "result": f.judgement["result"],
                        "extracted_value": 0.0,
                        "required_value": f.extracted_params.get("required_value", 1.0),
                        "difference": -f.extracted_params.get("required_value", 1.0),
                        "explanation": f.explanation[:120],
                    })

        # 统计
        entity_types = Counter(e["type"] for e in entities)
        violation_count = Counter(d["clause_id"] for d in details)

        file_result = {
            "filename": file.filename,
            "file_id": file_id,
            "status": "success",
            "summary": {
                "total_entities": len(entities),
                "entity_types": dict(entity_types),
                "violations": len(details),
                "violation_by_clause": dict(violation_count.most_common(10)),
            },
            "details": details[:100],
            "entities": [
                {"id": e.get("id", e.get("type", "")), "type": e["type"], "bbox": e["bbox"]}
                for e in entities
            ],
        }

        all_details.extend(details)
        all_entities.extend(entities)
        total_violations += len(details)
        total_checks += len(entities) * len(registry_funcs)
        results.append(file_result)

    # 交叉分析：跨图纸找出同一违规类别
    cross_clause = Counter(d["clause_id"] for d in all_details)
    cross_analysis = []
    for clause_id, count in cross_clause.most_common(10):
        involved_files = set()
        for r in results:
            if r["status"] != "success":
                continue
            for d in r["details"]:
                if d["clause_id"] == clause_id:
                    involved_files.add(r["filename"])
                    break
        cross_analysis.append({
            "clause_id": clause_id,
            "violations": count,
            "files": len(involved_files),
            "file_names": list(involved_files)[:5],
        })

    elapsed = int((time.time() - start) * 1000)

    return {
        "status": "success",
        "batch_summary": {
            "total_files": len(files),
            "success_files": sum(1 for r in results if r["status"] == "success"),
            "failed_files": sum(1 for r in results if r["status"] != "success"),
            "total_violations": total_violations,
            "total_checks": total_checks,
            "total_entities": len(all_entities),
            "processing_time_ms": elapsed,
        },
        "cross_analysis": cross_analysis,
        "results": results,
    }


@app.post("/review-from-data")
async def review_from_data(
    body: dict,
    request: Request = None,
    api_key: str = Depends(verify_api_key),
):
    """从已解析的结构化数据执行规范审查（无需重新上传文件）"""
    entities = body.get("entities", [])
    building_type = body.get("building_type", "civil")

    from src.baa_engine.spec_repository import SpecRepository
    from collections import Counter
    repo = SpecRepository()
    clause_results = Counter()
    details = []
    registry_funcs = _func_registry.list_all()

    start = time.time()

    for e in entities:
        for func in registry_funcs:
            threshold_val, unit, op = repo.get_threshold(func.clause_id, building_type)
            func.threshold = threshold_val
            func.unit = unit
            func.operator = op
            r = func.execute(e)
            if r is None:
                continue
            clause_results[func.clause_id] += 1
            if r.result != "PASS":
                clause = {
                    "standard": "GB50016",
                    "clause_id": func.clause_id,
                    "title": func.name,
                    "text": func.description,
                    "category": func.category.value,
                }
                f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])
                details.append({
                    "entity_id": e.get("id", e.get("type", "")),
                    "entity_type": e["type"],
                    "clause_id": f.clause.get("clause_id", ""),
                    "clause_title": f.clause.get("title", ""),
                    "result": f.judgement["result"],
                    "extracted_value": f.extracted_params["extracted_value"],
                    "required_value": f.extracted_params.get("required_value", 1.2),
                    "difference": f.extracted_params.get("difference", 0),
                    "severity": f.judgement.get("severity", "major"),
                    "explanation": f.explanation[:120],
                })

    # 缺失检查
    for func in registry_funcs:
        if func.category.value != "exist":
            continue
        has_match = any(func.matches(e) for e in entities)
        if not has_match:
            r = func.execute(None)
            if r is not None and r.result != "PASS":
                clause = {
                    "standard": "GB50016",
                    "clause_id": func.clause_id,
                    "title": func.name,
                    "text": func.description,
                    "category": func.category.value,
                }
                f = _attribution_analyzer.build_finding(r, clause, {}, entities[:5])
                details.append({
                    "entity_id": "",
                    "entity_type": "missing",
                    "clause_id": f.clause.get("clause_id", ""),
                    "clause_title": f.clause.get("title", ""),
                    "result": f.judgement["result"],
                    "severity": "critical",
                    "extracted_value": 0.0,
                    "required_value": f.extracted_params.get("required_value", 1.0),
                    "difference": -f.extracted_params.get("required_value", 1.0),
                    "explanation": f.explanation[:120],
                })

    elapsed = int((time.time() - start) * 1000)
    entity_types = Counter(e["type"] for e in entities)
    violation_count = Counter(d["clause_id"] for d in details)

    response_data = {
        "status": "success",
        "summary": {
            "total_entities": len(entities),
            "entity_types": dict(entity_types),
            "total_checks": len(entities) * len(registry_funcs),
            "violations": len(details),
            "violation_by_clause": dict(violation_count.most_common(10)),
        },
        "details": details[:100],
        "building_type": building_type,
        "processing_time_ms": elapsed,
    }

    # 修正建议
    try:
        from src.baa_engine.correction_engine import CorrectionEngine
        ce = CorrectionEngine()
        review_result_for_correction = {
            "findings": [{
                "entity_id": d["entity_id"],
                "entity_type": d["entity_type"],
                "clause_id": d["clause_id"],
                "clause_title": d["clause_title"],
                "extracted_value": d["extracted_value"],
                "required_value": d["required_value"],
                "difference": d["difference"],
            } for d in details]
        }
        corrections = ce.generate_for_result(review_result_for_correction)
        response_data["corrections"] = corrections
        # raw_result 供对比重构消费
        response_data["raw_result"] = {
            "elements": elements,
            "details": details,
            "corrections": corrections,
            "summary": response_data.get("summary", {}),
        }
    except Exception as e:
        response_data["corrections"] = []
        response_data["raw_result"] = {"elements": elements, "details": details}

    return response_data


@app.post("/reconstruct")
async def reconstruct(
    body: dict,
    request: Request = None,
    api_key: str = Depends(verify_api_key),
):
    """BIM 重构（需授权验证）"""
    file_id = body.get("file_id", "")
    auth_token = body.get("auth_token", "")

    # 验证授权
    auth_payload = verify_auth_token(auth_token)
    if auth_payload is None:
        raise HTTPException(
            status_code=402,
            detail={
                "status": "error",
                "error_code": "AUTH_FAILED",
                "message": "支付授权验证失败，请确认订单已支付",
            }
        )

    # 检查 file_id 是否存在
    file_path = get_file_path(file_id)
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "error_code": "FILE_NOT_FOUND",
                "message": f"文件不存在: {file_id}",
            }
        )

    # 执行重构（暂返回mock数据）
    order_id = f"baa-order-{uuid.uuid4().hex[:8]}"
    model_path = MODELS_DIR / order_id
    model_path.mkdir(parents=True, exist_ok=True)
    (model_path / "model.ifc").write_text(
        f"# Mock IFC file for order {order_id}\n"
        f"# Generated from file: {file_id}\n"
    )

    base_url = str(app.root_path) if app.root_path else "http://localhost:8000"

    return {
        "status": "success",
        "order_id": body.get("order_id", ""),
        "baa_order_id": order_id,
        "model_url": f"{base_url}/models/{order_id}/model.ifc",
        "elements_count": 40,
        "processing_time_ms": 15000,
        "file_size_mb": 2.5,
        "valid_until": (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z",
    }


@app.get("/order/{order_id}")
async def get_order(
    order_id: str,
    request: Request = None,
    api_key: str = Depends(verify_api_key),
):
    """订单状态查询"""
    order_dir = MODELS_DIR / order_id
    if not order_dir.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "error_code": "ORDER_NOT_FOUND",
                "message": "订单不存在",
            }
        )

    model_file = order_dir / "model.ifc"
    if model_file.exists():
        return {
            "status": "completed",
            "order_id": order_id,
            "progress": 100,
            "model_url": f"/models/{order_id}/model.ifc",
            "file_size_mb": round(model_file.stat().st_size / 1024 / 1024, 2),
        }
    else:
        return {
            "status": "processing",
            "order_id": order_id,
            "progress": 50,
            "estimated_remaining_ms": 15000,
        }


# ── 图纸渲染 ──────────────────────────────────────────────


@app.get("/render/{file_id}")
async def render_drawing(
    file_id: str,
    request: Request = None,
    api_key: str = Depends(verify_api_key),
):
    """将 DXF/DWG 图纸渲染为 SVG 供前端展示"""
    file_path = get_file_path(file_id)
    if not file_path:
        raise HTTPException(status_code=404, detail={"status": "error", "message": "文件不存在"})

    import ezdxf
    from io import StringIO

    try:
        doc = ezdxf.readfile(str(file_path))
        msp = doc.modelspace()
    except Exception:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "无法解析图纸文件"})

    # 计算边界
    all_x, all_y = [], []
    for entity in msp:
        try:
            if entity.dxftype() == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                all_x.extend([s[0], e[0]])
                all_y.extend([s[1], e[1]])
            elif entity.dxftype() == "LWPOLYLINE":
                pts = [(v[0], v[1]) for v in entity.get_points()]
                all_x.extend(p[0] for p in pts)
                all_y.extend(p[1] for p in pts)
            elif entity.dxftype() == "CIRCLE":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                all_x.extend([cx - r, cx + r])
                all_y.extend([cy - r, cy + r])
            elif entity.dxftype() in ("TEXT", "MTEXT"):
                ins = entity.dxf.insert[:2]
                all_x.append(ins[0])
                all_y.append(ins[1])
        except Exception:
            continue

    if not all_x:
        return {"status": "error", "message": "图纸无有效图元"}

    margin = 5.0
    x_min, x_max = min(all_x) - margin, max(all_x) + margin
    y_min, y_max = min(all_y) - margin, max(all_y) + margin
    w, h = x_max - x_min, y_max - y_min

    svg_w = min(max(w * 0.5, 400), 1200)
    svg_h = min(max(h * 0.5, 300), 800)

    buf = StringIO()
    buf.write(f'<svg xmlns="http://www.w3.org/2000/svg" '
              f'viewBox="{x_min} {-y_max} {w} {h}" '
              f'width="{svg_w}" height="{svg_h}" '
              f'style="background:#fff">\n')

    max_entities = 2000
    drawn = 0

    for entity in msp:
        if drawn >= max_entities:
            break
        dxftype = entity.dxftype()
        try:
            if dxftype == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                buf.write(f'<line x1="{s[0]:.2f}" y1="{-s[1]:.2f}" '
                          f'x2="{e[0]:.2f}" y2="{-e[1]:.2f}" '
                          f'stroke="#333" stroke-width="0.5" />\n')
                drawn += 1
            elif dxftype == "LWPOLYLINE":
                pts = [(v[0], -v[1]) for v in entity.get_points()]
                d = "M" + " L".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts)
                buf.write(f'<path d="{d}" fill="none" stroke="#333" stroke-width="0.5" />\n')
                drawn += 1
            elif dxftype == "CIRCLE":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                buf.write(f'<circle cx="{cx:.2f}" cy="{-cy:.2f}" r="{r:.2f}" '
                          f'fill="none" stroke="#333" stroke-width="0.5" />\n')
                drawn += 1
            elif dxftype in ("TEXT", "MTEXT"):
                ins = entity.dxf.insert[:2]
                txt = entity.dxf.text if hasattr(entity.dxf, 'text') else ''
                ht = entity.dxf.height if hasattr(entity.dxf, 'height') else 2.5
                buf.write(f'<text x="{ins[0]:.2f}" y="{-ins[1]:.2f}" '
                          f'font-size="{ht}" fill="#666">{txt[:30]}</text>\n')
                drawn += 1
        except Exception:
            continue

    buf.write('</svg>')
    svg_content = buf.getvalue()

    return Response(content=svg_content, media_type="image/svg+xml")


# ── 静态文件服务（模型下载） ─────────────────────────────

SPECS_DIR = DATA_DIR / "specs"

if SPECS_DIR.exists():
    app.mount("/data/specs", StaticFiles(directory=str(SPECS_DIR)), name="specs")

if MODELS_DIR.exists():
    app.mount("/models", StaticFiles(directory=str(MODELS_DIR)), name="models")


# ── API密钥管理端点 ──────────────────────────────────


@app.post("/admin/keys", tags=["admin"])
async def create_api_key(
    body: dict,
    request: Request = None,
    api_key: str = Depends(verify_api_key),
    _admin: str = Depends(require_admin),
):
    """创建新的API Key（需要admin权限）"""
    km = get_key_manager()

    permission = body.get("permission", "write")
    ttl_days = body.get("ttl_days", 90)
    label = body.get("label", "")

    try:
        result = km.generate_key(
            permission=permission,
            ttl_days=ttl_days,
            label=label,
            created_by=api_key or "anonymous"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={
            "status": "error", "error_code": "INVALID_PARAM",
            "message": str(e)
        })

    return {
        "status": "success",
        "data": result,
        "warning": "请立即保存 raw_key，创建后不再显示",
    }


@app.get("/admin/keys", tags=["admin"])
async def list_api_keys(
    include_disabled: bool = Query(False),
    include_raw: bool = Query(False, description="是否返回解密后的 raw_key（密钥详情时使用）"),
    request: Request = None,
    api_key: str = Depends(verify_api_key),
    _admin: str = Depends(require_admin),
):
    """列出所有API Key"""
    km = get_key_manager()
    keys = km.list_keys(include_disabled=include_disabled, include_raw=include_raw)
    stats = km.get_usage_stats()

    for k in keys:
        k_id = k["key_id"]
        if k_id in stats:
            k["usage"] = stats[k_id]

    return {
        "status": "success",
        "data": keys,
        "total": len(keys),
    }


@app.get("/admin/keys/stats", tags=["admin"])
async def api_key_stats(
    request: Request = None,
    api_key: str = Depends(verify_api_key),
    _admin: str = Depends(require_admin),
):
    """API Key用量统计"""
    km = get_key_manager()

    stats = km.get_usage_stats()
    keys = km.list_keys(include_disabled=True)

    return {
        "status": "success",
        "data": {
            "keys": stats,
            "summary": {
                "total": len(keys),
                "active": len([k for k in keys if k.get("enabled")]),
                "disabled": len([k for k in keys if not k.get("enabled")]),
                "total_calls": sum(s.get("total_calls", 0) for s in stats.values()),
            }
        }
    }


@app.get("/admin/keys/{key_id}", tags=["admin"])
async def get_api_key_detail(
    key_id: str,
    request: Request = None,
    api_key: str = Depends(verify_api_key),
    _admin: str = Depends(require_admin),
):
    """获取单个API Key详情（含解密后的 raw_key）"""
    km = get_key_manager()
    keys = km.list_keys(include_disabled=True, include_raw=True)
    for k in keys:
        if k["key_id"] == key_id:
            stats = km.get_usage_stats(key_id)
            k["usage"] = stats
            return {"status": "success", "data": k}
    raise HTTPException(status_code=404, detail={
        "status": "error", "error_code": "NOT_FOUND",
        "message": f"密钥不存在: {key_id}"
    })


@app.post("/admin/keys/{key_id}/revoke", tags=["admin"])
async def revoke_api_key(
    key_id: str,
    request: Request = None,
    api_key: str = Depends(verify_api_key),
    _admin: str = Depends(require_admin),
):
    """撤销API Key"""
    km = get_key_manager()

    if km.revoke_key(key_id):
        return {"status": "success", "message": f"密钥 {key_id} 已撤销"}
    raise HTTPException(status_code=404, detail={
        "status": "error", "error_code": "NOT_FOUND",
        "message": f"密钥不存在: {key_id}"
    })


@app.post("/admin/keys/{key_id}/rotate", tags=["admin"])
async def rotate_api_key(
    key_id: str,
    body: dict,
    request: Request = None,
    api_key: str = Depends(verify_api_key),
    _admin: str = Depends(require_admin),
):
    """轮换API Key（生成新密钥值，旧密钥失效）"""
    km = get_key_manager()
    result = km.rotate_key(key_id, new_ttl_days=new_ttl)
    if result:
        return {
            "status": "success",
            "data": result,
            "warning": "旧密钥已失效，请立即保存新 raw_key",
        }
    raise HTTPException(status_code=404, detail={
        "status": "error", "error_code": "NOT_FOUND",
        "message": f"密钥不存在或已禁用: {key_id}"
    })


@app.delete("/admin/keys/{key_id}", tags=["admin"])
async def delete_api_key(
    key_id: str,
    request: Request = None,
    api_key: str = Depends(verify_api_key),
    _admin: str = Depends(require_admin),
):
    """物理删除API Key（不可恢复）"""
    km = get_key_manager()
    if km.delete_key(key_id):
        return {"status": "success", "message": f"密钥 {key_id} 已永久删除"}
    raise HTTPException(status_code=404, detail={
        "status": "error", "error_code": "NOT_FOUND",
        "message": f"密钥不存在: {key_id}"
    })


@app.post("/admin/keys/verify", tags=["admin"])
async def verify_api_key_raw(
    body: dict,
    request: Request = None,
):
    """验证原始API Key是否有效（无需admin权限，供前端导入时校验）"""
    raw_key = body.get("raw_key", "")
    if not raw_key:
        return {"status": "error", "valid": False, "message": "请提供 raw_key"}

    km = get_key_manager()
    key_info = km.validate_key(raw_key)
    if key_info and key_info.get("enabled", True):
        return {
            "status": "success",
            "valid": True,
            "key_info": {
                "key_id": key_info.get("key_id"),
                "label": key_info.get("label"),
                "permission": key_info.get("permission"),
                "expires_at": key_info.get("expires_at"),
                "created_at": key_info.get("created_at"),
            }
        }
    else:
        return {
            "status": "success",
            "valid": False,
            "message": "密钥无效或已过期/撤销"
        }


@app.get("/admin/bootstrap-key", tags=["admin"])
async def bootstrap_admin_key():
    """获取前端密钥管理页使用的管理令牌（免认证）
    
    开发模式（BAA_API_KEY 未设置）时返回空字符串，
    此时后端 require_admin 不校验令牌，前端直接发请求即可。
    生产模式时返回环境变量中的 admin key。
    """
    env_key = os.getenv("BAA_API_KEY", "")
    return {
        "status": "success",
        "admin_key": env_key,
        "mode": "production" if env_key else "development",
    }


# ── 启动入口 ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    import sys
    import os
    port = int(os.getenv("BAA_PORT", "8000"))
    workers = int(os.getenv("BAA_WORKERS", "4"))  # 默认4 worker

    # 日志输出到项目 data/logs/ 下
    log_dir = DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "baa-api.log"
    print(f"[BAA] 日志路径: {log_file}", flush=True)
    print(f"[BAA] Worker 数: {workers}", flush=True)

    uvicorn.run(
        "src.api.baa_api:app",
        host="0.0.0.0",
        port=port,
        workers=workers,
        log_config=None,
        access_log=False,
        log_level="info"
    )