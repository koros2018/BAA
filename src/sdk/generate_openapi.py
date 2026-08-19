#!/usr/bin/env python3
"""
P89: 导出 OpenAPI 3.0 JSON schema

生成步骤:
1. 启动 FastAPI 应用 (加载所有 routes)
2. 使用 fastapi.openapi.utils.get_openapi 导出 JSON
3. 写入 src/sdk/openapi.json

用法:
    python3 src/sdk/generate_openapi.py
"""

import os
import sys
import json

# 确保项目根在 sys.path 中
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)


def main():
    """程序入口，生成 OpenAPI 规范文件。"""
    print("[openapi] 加载 FastAPI 应用...")
    from src.api.baa_api import app

    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": app.title,
            "description": "BAA (Blueprint AI Agent) — 建筑图纸 AI 合规审查系统",
            "version": app.version if hasattr(app, "version") and app.version else "2.5.29",
        },
        "servers": [
            {"url": "http://localhost:8000", "description": "本地开发"},
            {"url": "https://api.baa.example.com", "description": "生产环境 (占位)"},
        ],
    }

    # 从 FastAPI 提取 path items 和 components
    spec["paths"] = {}
    spec["components"] = {}

    for route in app.routes:
        if not hasattr(route, "path"):
            continue
        if not hasattr(route, "methods"):
            continue
        # 跳过内部 OpenAPI/Docs/Swagger 路由
        if route.path in (
            "/openapi.json",
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
            "/favicon.ico",
            "/",
        ):
            continue

        path_item = spec["paths"].setdefault(route.path, {})
        for method in route.methods:
            method_lower = method.lower()
            if method_lower in ("options", "head"):
                continue
            path_item[method_lower] = {
                "summary": getattr(route, "summary", "") or route.name or "",
                "description": getattr(route, "description", "") or route.name or "",
                "tags": getattr(route, "tags", []),
                "operationId": route.name or f"{method_lower}_{route.path.replace('/', '_')}",
                "security": [{"ApiKeyAuth": []}] if route.path not in ("/health", "/") else [],
            }

    # 添加 securitySchemes 组件
    spec["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "Bearer token, 格式: Bearer <api_key>",
        }
    }

    # 写文件
    out_dir = os.path.dirname(__file__)
    out_path = os.path.join(out_dir, "openapi.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)

    route_count = sum(len(v) for v in spec["paths"].values())
    print(f"[openapi] ✅ 导出完成: {out_path}")
    print(f"[openapi] 路径数: {len(spec['paths'])}, 操作数: {route_count}")
    return out_path


if __name__ == "__main__":
    main()
