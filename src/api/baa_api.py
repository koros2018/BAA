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

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Security, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


# ── 配置 ──────────────────────────────────────────────────

# ── 项目工作路径（默认：项目根目录下的 data/） ───────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # src/../
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
AUTH_SECRETS = [s.strip() for s in os.getenv("BAA_AUTH_SECRET", "baa-dev-secret-change-in-production").split(",") if s.strip()]


# ── 授权验证 ──────────────────────────────────────────────

import hmac
import hashlib
import base64


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

app = FastAPI(title="BAA API", version="1.0.0")
security = HTTPBearer()

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


def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """验证 Bearer Token"""
    if API_KEYS and credentials.credentials not in API_KEYS:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "error_code": "INVALID_API_KEY",
                    "message": "API Key 无效"}
        )
    return credentials.credentials


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

_engine_modules_loaded = False
_drawing_parser = None
_semantic_analyzer = None
_func_registry = None
_attribution_analyzer = None


def _ensure_engine():
    global _engine_modules_loaded, _drawing_parser, _semantic_analyzer, _func_registry, _attribution_analyzer
    if _engine_modules_loaded:
        return
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.semantic_analyzer import SemanticAnalyzer
    from src.baa_engine.atomic_functions import FuncRegistry
    from src.baa_engine.attribution_analyzer import AttributionAnalyzer
    _drawing_parser = DrawingParser()
    _semantic_analyzer = SemanticAnalyzer()
    _func_registry = FuncRegistry()
    _attribution_analyzer = AttributionAnalyzer()
    _engine_modules_loaded = True

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "uptime_seconds": 0,
        "engine_status": "ready",
        "supported_formats": list(SUPPORTED_FORMATS),
        "api_version": "v1",
    }


@app.post("/deconstruct")
async def deconstruct(
    file: UploadFile = File(...),
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
    _ensure_engine()

    # Step 1: 图纸解析
    result = _drawing_parser.parse(str(file_path), file_id=file_id)
    if not result.success:
        return {
            "status": "error",
            "error_code": "PARSE_FAILED",
            "message": f"图纸解析失败: {result.error}",
            "file_id": file_id,
        }

    # Step 2: 语义分析（限制采样1000个防OOM）
    semantic = _semantic_analyzer.analyze(result.primitives, result.dimensions)
    entities = semantic["entities"]
    relations = semantic["relations"]

    # Step 3: 规范判定
    findings = []
    registry_funcs = _func_registry.list_all()
    total_checks = 0
    for e in entities:
        for func in registry_funcs:
            total_checks += 1
            r = func.execute(e)
            if r.result != "PASS":
                clause = {
                    "standard": "GB50016",
                    "clause_id": func.clause_id,
                    "title": func.name,
                    "text": func.description,
                    "category": func.category.value,
                }
                f = _attribution_analyzer.build_finding(r, clause, e, entities[:5])
                findings.append(f.finding_id)

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

    return {
        "status": "success",
        "elements": elements,
        "relations": len(relations),
        "findings": len(findings),
        "total_checks": total_checks,
        "confidence": 0.85 if len(entities) > 0 else 0,
        "file_id": file_id,
        "processing_time_ms": elapsed,
    }


@app.post("/review")
async def review(
    file: UploadFile = File(...),
    full: bool = Query(False, description="返回完整图元列表"),
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
    _ensure_engine()

    # 解析
    result = _drawing_parser.parse(str(file_path), file_id=file_id)
    if not result.success:
        return {
            "status": "error",
            "error_code": "PARSE_FAILED",
            "message": f"图纸解析失败: {result.error}",
            "file_id": file_id,
        }

    # 语义分析（采样1000限制）
    semantic = _semantic_analyzer.analyze(result.primitives, result.dimensions)
    entities = semantic["entities"]

    # 规范判定
    from collections import Counter
    clause_results = Counter()
    details = []
    registry_funcs = _func_registry.list_all()
    for e in entities:
        for func in registry_funcs:
            r = func.execute(e)
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
                    "entity_id": e["id"],
                    "entity_type": e["type"],
                    "clause_id": f.clause.get("clause_id", ""),
                    "clause_title": f.clause.get("title", ""),
                    "result": f.judgement["result"],
                    "extracted_value": f.extracted_params["extracted_value"],
                    "required_value": f.extracted_params.get("required_value", 1.2),
                    "difference": f.extracted_params.get("difference", 0),
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
        "processing_time_ms": elapsed,
    }

    if full:
        response_data["all_entities"] = [
            {"id": e["id"], "type": e["type"], "bbox": e["bbox"]}
            for e in entities
        ]

    return response_data


@app.post("/reconstruct")
async def reconstruct(
    body: dict,
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


# ── 静态文件服务（模型下载） ─────────────────────────────

if MODELS_DIR.exists():
    app.mount("/models", StaticFiles(directory=str(MODELS_DIR)), name="models")


# ── 启动入口 ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    import sys
    port = int(os.getenv("BAA_PORT", "8000"))

    # 日志输出到项目 data/logs/ 下
    log_dir = DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "baa-api.log"
    print(f"[BAA] 日志路径: {log_file}", flush=True)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_config=None,
        access_log=False,
        log_level="info"
    )