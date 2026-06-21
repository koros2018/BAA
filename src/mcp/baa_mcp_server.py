"""
BAA MCP Server - 将BAA图纸解构和BIM重构能力封装为MCP工具
基于 DD-9 MCP与Skill接入方案 v4.0（终稿定稿）

启动方式：
  # Streamable HTTP（推荐，适用于远程部署）
  python src/mcp/baa_mcp_server.py --transport streamable-http --port 8080

  # Stdio（适用于本地或容器内）
  python src/mcp/baa_mcp_server.py --transport stdio
"""
import json
import os
import sys
import asyncio
from pathlib import Path
from typing import Any, Optional

# 添加项目根到路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent
from mcp.server.lowlevel.helper_types import ReadResourceContents

from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.semantic_analyzer import SemanticAnalyzer
from src.baa_engine.atomic_functions import FuncRegistry
from src.baa_engine.attribution_analyzer import AttributionAnalyzer
from src.baa_engine.spec_repository import SpecRepository
from src.api.baa_api import generate_auth_token, verify_auth_token


class BAAMCPServer:
    """BAA MCP Server"""

    def __init__(self):
        # 懒加载引擎
        self._drawing_parser: Optional[DrawingParser] = None
        self._semantic_analyzer: Optional[SemanticAnalyzer] = None
        self._func_registry: Optional[FuncRegistry] = None
        self._attribution_analyzer: Optional[AttributionAnalyzer] = None
        self._spec_repo: Optional[SpecRepository] = None

        self.server = Server("baa-blueprint")

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="baa_deconstruct",
                    description="解构工程图纸，识别墙、柱、梁、板、门、窗、楼梯、电梯等构件，返回结构化数据。此工具免费使用。",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "图纸文件路径（支持 dxf/dwg，推荐 dxf）"
                            },
                            "building_type": {
                                "type": "string",
                                "description": "建筑类型: civil(民用) / industrial(工业)，默认 civil",
                                "default": "civil"
                            }
                        },
                        "required": ["file_path"]
                    }
                ),
                Tool(
                    name="baa_reconstruct",
                    description="基于解构结果生成 BIM 模型。此工具需要有效的授权令牌（auth_token）。",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_id": {
                                "type": "string",
                                "description": "解构接口返回的 file_id"
                            },
                            "auth_token": {
                                "type": "string",
                                "description": "授权代收代付点生成的支付授权令牌（JWT格式）"
                            },
                            "elements": {
                                "type": "array",
                                "description": "构件列表（可选，不传则使用 file_id 关联数据）",
                                "items": {"type": "object"}
                            },
                            "options": {
                                "type": "object",
                                "description": "重构参数（可选）",
                                "properties": {
                                    "lod": {"type": "integer", "description": "LOD等级: 100/200/300"},
                                    "format": {"type": "string", "description": "输出格式: ifc/obj/fbx"},
                                    "include_reinforcement": {"type": "boolean"}
                                }
                            }
                        },
                        "required": ["file_id", "auth_token"]
                    }
                ),
                Tool(
                    name="baa_review",
                    description="图纸合规审查，基于GB50016规范检查图纸违规项。此工具免费使用。",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "图纸文件路径（支持 dxf/dwg）"
                            },
                            "building_type": {
                                "type": "string",
                                "description": "建筑类型: civil(民用) / industrial(工业)，默认 civil"
                            }
                        },
                        "required": ["file_path"]
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            try:
                if name == "baa_deconstruct":
                    result = await self._handle_deconstruct(arguments)
                elif name == "baa_reconstruct":
                    result = await self._handle_reconstruct(arguments)
                elif name == "baa_review":
                    result = await self._handle_review(arguments)
                else:
                    raise ValueError(f"未知工具: {name}")

                return [TextContent(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False, indent=2)
                )]
            except Exception as e:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "status": "error",
                        "error_code": type(e).__name__,
                        "message": str(e)
                    }, ensure_ascii=False)
                )]

    def _ensure_engine(self):
        """懒加载引擎模块"""
        if self._drawing_parser is not None:
            return
        self._drawing_parser = DrawingParser()
        self._semantic_analyzer = SemanticAnalyzer()
        self._func_registry = FuncRegistry()
        self._attribution_analyzer = AttributionAnalyzer()
        self._spec_repo = SpecRepository()

    async def _handle_deconstruct(self, args: dict) -> dict:
        """图纸解构"""
        self._ensure_engine()
        file_path = args["file_path"]
        building_type = args.get("building_type", "civil")

        # 检查文件存在
        if not os.path.exists(file_path):
            return {"status": "error", "error_code": "FILE_NOT_FOUND",
                    "message": f"文件不存在: {file_path}"}

        # Step 1: 图纸解析
        file_id = f"baa-file-mcp-{os.path.basename(file_path)}"
        result = self._drawing_parser.parse(file_path, file_id=file_id)
        if not result.success:
            return {"status": "error", "error_code": "PARSE_FAILED",
                    "message": f"图纸解析失败: {result.error}"}

        # Step 2: 语义分析
        semantic = self._semantic_analyzer.analyze(
            result.primitives, result.dimensions, building_type=building_type
        )
        entities = semantic["entities"]

        # 统计构件
        type_stats = {}
        for e in entities:
            t = e["type"]
            if t not in type_stats:
                type_stats[t] = {"count": 0, "bbox_areas": []}
            type_stats[t]["count"] += 1
            bbox = e["bbox"]
            type_stats[t]["bbox_areas"].append(
                bbox.get("width", 0) * bbox.get("height", 0)
            )

        elements = []
        for t, stats in sorted(type_stats.items()):
            areas = stats["bbox_areas"]
            elem = {"type": t, "count": stats["count"]}
            total_area = sum(areas) if areas else 0
            if t in ("wall", "corridor", "stair"):
                elem["total_length_m"] = round(total_area ** 0.5, 1)
            elif t in ("door", "fire_door", "window"):
                elem["total_count"] = stats["count"]
            elif t == "fire_zone":
                elem["total_area_sqm"] = round(total_area, 1)
            elements.append(elem)

        return {
            "status": "success",
            "elements": elements,
            "entity_count": len(entities),
            "relations": len(semantic["relations"]),
            "confidence": 0.85 if len(entities) > 0 else 0,
            "file_id": file_id,
            "building_type": building_type,
        }

    async def _handle_reconstruct(self, args: dict) -> dict:
        """BIM 重构"""
        self._ensure_engine()
        file_id = args["file_id"]
        auth_token = args["auth_token"]

        # 验证授权
        auth_payload = verify_auth_token(auth_token)
        if auth_payload is None:
            return {"status": "error", "error_code": "AUTH_FAILED",
                    "message": "支付授权验证失败，请确认订单已支付"}

        # 生成 mock IFC 输出
        order_id = f"baa-order-mcp-{file_id[-8:]}"
        options = args.get("options", {})
        lod = options.get("lod", 200) if isinstance(options, dict) else 200
        fmt = options.get("format", "ifc") if isinstance(options, dict) else "ifc"

        return {
            "status": "success",
            "order_id": order_id,
            "model_file": f"{order_id}.{fmt}",
            "lod": lod,
            "format": fmt,
            "elements_count": len(args.get("elements", [])),
            "auth_info": {
                "client_id": auth_payload.get("client_id", "unknown"),
                "service": auth_payload.get("service", "reconstruct"),
                "expires_at": auth_payload.get("expires_at", "unknown"),
            }
        }

    async def _handle_review(self, args: dict) -> dict:
        """图纸合规审查"""
        self._ensure_engine()
        file_path = args["file_path"]
        building_type = args.get("building_type", "civil")

        if not os.path.exists(file_path):
            return {"status": "error", "error_code": "FILE_NOT_FOUND",
                    "message": f"文件不存在: {file_path}"}

        file_id = f"baa-file-mcp-{os.path.basename(file_path)}"
        result = self._drawing_parser.parse(file_path, file_id=file_id)
        if not result.success:
            return {"status": "error", "error_code": "PARSE_FAILED",
                    "message": f"图纸解析失败: {result.error}"}

        semantic = self._semantic_analyzer.analyze(
            result.primitives, result.dimensions, building_type=building_type
        )
        entities = semantic["entities"]

        # 规范判定
        findings = []
        from collections import Counter
        clause_results = Counter()
        registry_funcs = self._func_registry.list_all()
        total_checks = 0

        for e in entities:
            for func in registry_funcs:
                total_checks += 1
                threshold_val, unit, op = self._spec_repo.get_threshold(
                    func.clause_id, building_type
                )
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
                    f = self._attribution_analyzer.build_finding(
                        r, clause, e, entities[:5]
                    )
                    findings.append({
                        "entity_id": e["id"],
                        "entity_type": e["type"],
                        "clause_id": f.clause.get("clause_id", ""),
                        "clause_title": f.clause.get("title", ""),
                        "result": f.judgement["result"],
                        "extracted_value": r.actual,
                        "required_value": r.threshold,
                        "difference": abs(r.delta),
                        "explanation": f.explanation[:200] if f.explanation else "",
                    })

        entity_types = Counter(e["type"] for e in entities)
        violation_count = Counter(f["clause_id"] for f in findings)

        return {
            "status": "success",
            "summary": {
                "total_entities": len(entities),
                "entity_types": dict(entity_types),
                "total_checks": total_checks,
                "violations": len(findings),
                "violation_by_clause": dict(violation_count.most_common(10)),
            },
            "findings": findings[:50],
            "file_id": file_id,
            "building_type": building_type,
        }

    async def run_stdio(self):
        """通过 stdio 运行 MCP Server"""
        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="baa-blueprint",
                    server_version="1.2.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    async def run_http(self, host: str = "0.0.0.0", port: int = 8080):
        """通过 Streamable HTTP 运行 MCP Server"""
        from mcp.server.http import run_server
        await run_server(self.server, host=host, port=port)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="BAA MCP Server")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"],
                        default="stdio")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    server = BAAMCPServer()

    if args.transport == "stdio":
        asyncio.run(server.run_stdio())
    else:
        asyncio.run(server.run_http(host=args.host, port=args.port))


if __name__ == "__main__":
    main()
