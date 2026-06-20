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

DATA_DIR = Path(os.getenv("BAA_DATA_DIR", "/tmp/baa"))
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

# 共享密钥（用于 auth_token 验证）
AUTH_SECRET = os.getenv("BAA_AUTH_SECRET", "baa-dev-secret-change-in-production")


# ── 授权验证 ──────────────────────────────────────────────

import hmac
import hashlib
import base64


def generate_auth_token(payload: dict) -> str:
    """生成 auth_token（JWT格式，HMAC-SHA256）"""
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(
        json.dumps(header).encode()).rstrip(b"=").decode()
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload).encode()).rstrip(b"=").decode()
    signing_input = f"{header_b64}.{payload_b64}"
    sig = hmac.new(
        AUTH_SECRET.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_auth_token(token: str) -> Optional[dict]:
    """验证 auth_token"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"

        # 补回 padding
        def add_padding(s):
            return s + "=" * (4 - len(s) % 4)

        expected_sig = hmac.new(
            AUTH_SECRET.encode(), signing_input.encode(), hashlib.sha256
        ).digest()

        actual_sig = base64.urlsafe_b64decode(add_padding(sig_b64))
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload = json.loads(base64.urlsafe_b64decode(add_padding(payload_b64)))

        # 验证有效期
        expires = payload.get("expires_at")
        if expires:
            exp_time = datetime.fromisoformat(expires)
            if datetime.utcnow() > exp_time:
                return None

        return payload
    except Exception:
        return None


# ── FastAPI 应用 ──────────────────────────────────────────

app = FastAPI(title="BAA API", version="1.0.0")
security = HTTPBearer()

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


# ── 端点 ──────────────────────────────────────────────────

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
    store_file(content, file_id, ext)

    # 调用核心引擎进行解析（暂返回mock数据）
    start = time.time()
    elements = [
        {"type": "wall", "count": 12, "total_length": 45.6},
        {"type": "column", "count": 8, "total_volume": 15.2},
        {"type": "beam", "count": 16, "total_length": 62.4},
        {"type": "slab", "count": 4, "total_area": 320.0},
        {"type": "door", "count": 10, "note": "含防火门2个"},
        {"type": "window", "count": 8, "total_area": 45.0},
        {"type": "stair", "count": 2, "note": "疏散楼梯"},
    ]
    elapsed = int((time.time() - start) * 1000)

    return {
        "status": "success",
        "elements": elements,
        "confidence": 0.92,
        "file_id": file_id,
        "processing_time_ms": elapsed,
    }


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
    port = int(os.getenv("BAA_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)