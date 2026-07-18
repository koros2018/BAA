"""
BAA MCP Server — 将 BAA 图纸解构/BIM 重构/合规审查能力封装为 MCP 工具
"""

import json
import os
import sys
import asyncio
import time
from pathlib import Path
from typing import Any, Optional
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent, Resource
from mcp.server.lowlevel.helper_types import ReadResourceContents

from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.semantic_analyzer import SemanticAnalyzer
from src.baa_engine.atomic_functions import FuncRegistry
from src.baa_engine.attribution_analyzer import AttributionAnalyzer
from src.baa_engine.spec_repository import SpecRepository
from src.api.baa_api import generate_auth_token, verify_auth_token


class BAAMCPServer:
    """BAA MCP Server — 将图纸审查能力封装为 MCP 工具"""

    def __init__(self):
        self._drawing_parser: Optional[DrawingParser] = None
        self._semantic_analyzer: Optional[SemanticAnalyzer] = None
        self._func_registry: Optional[FuncRegistry] = None
        self._attribution_analyzer: Optional[AttributionAnalyzer] = None
        self._spec_repo: Optional[SpecRepository] = None
        self._thread_pool = ThreadPoolExecutor(max_workers=2)

        self.server = Server("baa-blueprint")

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(name="baa_deconstruct",
                     description="解构工程图纸，识别墙、柱、梁、板、门、窗、楼梯、电梯等构件，返回结构化数据。此工具免费使用。",
                     inputSchema={"type": "object", "properties": {
                         "file_path": {"type": "string", "description": "图纸文件路径（支持 dxf/dwg）"},
                         "building_type": {"type": "string", "description": "建筑类型: civil(民用) / industrial(工业)，默认 civil"},
                     }, "required": ["file_path"]}),
                Tool(name="baa_review",
                     description="图纸合规审查，基于 GB50016/GB50974/GB50763/GB50067 规范检查图纸违规项。此工具免费使用。",
                     inputSchema={"type": "object", "properties": {
                         "file_path": {"type": "string", "description": "图纸文件路径（支持 dxf/dwg）"},
                         "building_type": {"type": "string", "description": "建筑类型: civil(民用) / industrial(工业)，默认 civil"},
                     }, "required": ["file_path"]}),
                Tool(name="baa_reconstruct",

                     description="检查 BAA 引擎健康状态，包括各子系统就绪状态、原子函数数、规范数。此工具免费使用。",
                     inputSchema={"type": "object", "properties": {}, "required": []}),
                Tool(name="baa_list_functions",
                     description="列出所有注册的原子函数，支持按类别筛选。此工具免费使用。",
                     inputSchema={"type": "object", "properties": {
                         "category": {"type": "string", "description": "筛选类别: dim / dist / exist / count / area / attr / access / evac"},
                     }, "required": []}),
                Tool(name="baa_review_from_data",
                     description="从已有实体数据（而非图纸文件）执行规范审查。此工具免费使用。",
                     inputSchema={"type": "object", "properties": {
                         "entities": {"type": "array", "description": "实体列表", "items": {"type": "object"}},
                         "building_type": {"type": "string", "description": "建筑类型，默认 civil"},
                     }, "required": ["entities"]}),
            ]

        @self.server.list_resources()
        async def list_resources() -> list[Resource]:
            return [
                Resource(uri="baa://functions/count", name="原子函数总数",
                         description=f"当前注册原子函数数: {self._get_func_count()} / 260", mimeType="application/json"),
                Resource(uri="baa://specs/list", name="已加载规范列表",
                         description="BAA 支持的所有建筑规范", mimeType="application/json"),
            ]

        @self.server.read_resource()
        async def read_resource(uri: str) -> ReadResourceContents:
            self._ensure_engine()
            if uri == "baa://functions/count":
                return ReadResourceContents(
                    content=json.dumps({"count": self._func_registry.count, "capacity": self._func_registry.capacity},
                                      ensure_ascii=False),
                    mime_type="application/json")
            elif uri == "baa://specs/list":
                return ReadResourceContents(
                    content=json.dumps({"GB50016": "建筑设计防火规范", "GB50067": "汽车库设计防火规范",
                                       "GB50763": "无障碍设计规范", "GB50974": "消防给水及消火栓系统技术规范"},
                                      ensure_ascii=False),
                    mime_type="application/json")
            raise ValueError(f"未知 resource URI: {uri}")

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            try:
                handlers = {"baa_deconstruct": self._handle_deconstruct, "baa_review": self._handle_review,
                            "baa_reconstruct": self._handle_reconstruct, "baa_health": self._handle_health,
                            "baa_list_functions": self._handle_list_functions,
                            "baa_review_from_data": self._handle_review_from_data}
                handler = handlers.get(name)
                if handler is None:
                    raise ValueError(f"未知工具: {name}")
                result = await handler(arguments)
                return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            except Exception as e:
                return [TextContent(type="text",
                                    text=json.dumps({"status": "error", "error_code": type(e).__name__, "message": str(e)},
                                                    ensure_ascii=False))]

    def _get_func_count(self) -> int:
        return self._func_registry.count if self._func_registry else 0

    def _ensure_engine(self):
        if self._drawing_parser is not None:
            return
        self._drawing_parser = DrawingParser()
        self._semantic_analyzer = SemanticAnalyzer()
        self._func_registry = FuncRegistry()
        self._attribution_analyzer = AttributionAnalyzer()
        self._spec_repo = SpecRepository()

    async def _handle_health(self, args: dict) -> dict:
        self._ensure_engine()
        return {"status": "ok", "version": "1.25.0",
                "engine": {"drawing_parser": "ready", "semantic_analyzer": "ready",
                           "func_registry": f"{self._func_registry.count}/{self._func_registry.capacity}",
                           "spec_repo": f"{self._spec_repo.count} 条规范"}}

    async def _handle_list_functions(self, args: dict) -> dict:
        self._ensure_engine()
        cat = args.get("category", "").strip().lower()
        funcs = self._func_registry.list_all()
        if cat:
            funcs = [f for f in funcs if f.category.value == cat]
        return {"total": len(funcs), "capacity": self._func_registry.capacity,
                "categories": dict(Counter(f.category.value for f in funcs)),
                "functions": [{"id": f.func_id, "name": f.name, "category": f.category.value,
                               "clause": f.clause_id, "description": f.description,
                               "threshold": f.threshold, "unit": f.unit, "operator": f.operator} for f in funcs]}

    async def _handle_deconstruct(self, args: dict) -> dict:
        self._ensure_engine()
        file_path = args["file_path"]
        building_type = args.get("building_type", "civil")
        if not os.path.exists(file_path):
            return {"status": "error", "error_code": "FILE_NOT_FOUND", "message": f"文件不存在: {file_path}"}
        file_id = f"baa-file-mcp-{os.path.basename(file_path)}"
        result = self._drawing_parser.parse(file_path, file_id=file_id)
        if not result.success:
            return {"status": "error", "error_code": "PARSE_FAILED", "message": f"图纸解析失败: {result.error}"}
        semantic = self._semantic_analyzer.analyze(result.primitives, result.dimensions, building_type=building_type)
        entities = semantic["entities"]
        type_stats = {}
        for e in entities:
            t = e["type"]
            if t not in type_stats:
                type_stats[t] = {"count": 0, "bbox_areas": []}
            type_stats[t]["count"] += 1
            type_stats[t]["bbox_areas"].append(e["bbox"].get("width", 0) * e["bbox"].get("height", 0))
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
            elements.append(elem)
        return {"status": "success", "elements": elements, "entity_count": len(entities),
                "relations": len(semantic["relations"]), "confidence": 0.85 if entities else 0,
                "file_id": file_id, "building_type": building_type}

    async def _handle_review(self, args: dict) -> dict:
        self._ensure_engine()
        file_path = args["file_path"]
        building_type = args.get("building_type", "civil")
        if not os.path.exists(file_path):
            return {"status": "error", "error_code": "FILE_NOT_FOUND", "message": f"文件不存在: {file_path}"}
        file_id = f"baa-file-mcp-{os.path.basename(file_path)}"
        result = self._drawing_parser.parse(file_path, file_id=file_id)
        if not result.success:
            return {"status": "error", "error_code": "PARSE_FAILED", "message": f"图纸解析失败: {result.error}"}
        semantic = self._semantic_analyzer.analyze(result.primitives, result.dimensions, building_type=building_type)
        entities = semantic["entities"]
        loop = asyncio.get_event_loop()
        findings, total_checks = await loop.run_in_executor(self._thread_pool, self._do_clustering, entities, building_type)
        return {"status": "success",
                "summary": {"total_entities": len(entities),
                            "entity_types": dict(Counter(e["type"] for e in entities)),
                            "total_checks": total_checks, "violations": len(findings),
                            "violation_by_clause": dict(Counter(f["clause_id"] for f in findings).most_common(10))},
                "findings": findings[:50], "file_id": file_id, "building_type": building_type}

    def _do_clustering(self, entities: list, building_type: str) -> tuple:
        findings = []
        registry_funcs = self._func_registry.list_all()
        total_checks = 0
        for e in entities:
            for func in registry_funcs:
                total_checks += 1
                try:
                    tv, u, op = self._spec_repo.get_threshold(func.clause_id, building_type)
                    func.threshold = tv; func.unit = u; func.operator = op
                except Exception:
                    pass
                r = func.execute(e)
                if r is None or r.result == "PASS":
                    continue
                clause = {"standard": "GB50016", "clause_id": func.clause_id, "title": func.name,
                          "text": func.description, "category": func.category.value}
                f = self._attribution_analyzer.build_finding(r, clause, e, entities[:5])
                findings.append({"entity_id": e["id"], "entity_type": e["type"],
                                 "clause_id": f.clause.get("clause_id", ""),
                                 "clause_title": f.clause.get("title", ""),
                                 "result": f.judgement["result"], "extracted_value": r.actual,
                                 "required_value": r.threshold, "difference": abs(r.delta),
                                 "explanation": (f.explanation[:200] if f.explanation else "")})
        return findings, total_checks

    async def _handle_review_from_data(self, args: dict) -> dict:
        self._ensure_engine()
        entities = args["entities"]
        building_type = args.get("building_type", "civil")
        loop = asyncio.get_event_loop()
        findings, total_checks = await loop.run_in_executor(self._thread_pool, self._do_clustering, entities, building_type)
        return {"status": "success",
                "summary": {"total_entities": len(entities), "total_checks": total_checks, "violations": len(findings)},
                "findings": findings[:50]}

    async def _handle_reconstruct(self, args: dict) -> dict:
        self._ensure_engine()
        auth_payload = verify_auth_token(args["auth_token"])
        if auth_payload is None:
            return {"status": "error", "error_code": "AUTH_FAILED", "message": "支付授权验证失败"}
        file_id = args["file_id"]
        order_id = f"baa-order-mcp-{file_id[-8:]}"
        options = args.get("options", {})
        lod = options.get("lod", 200) if isinstance(options, dict) else 200
        fmt = options.get("format", "ifc") if isinstance(options, dict) else "ifc"
        return {"status": "success", "order_id": order_id, "model_file": f"{order_id}.{fmt}",
                "lod": lod, "format": fmt, "elements_count": len(args.get("elements", [])),
                "auth_info": {"client_id": auth_payload.get("client_id", "unknown"),
                              "service": auth_payload.get("service", "reconstruct")}}

    async def run_stdio(self):
        from mcp.server.stdio import stdio_server
        async with stdio_server() as (rs, ws):
            await self.server.run(rs, ws,
                                  InitializationOptions(server_name="baa-blueprint", server_version="1.3.0",
                                                       capabilities=self.server.get_capabilities(
                                                           notification_options=NotificationOptions(),
                                                           experimental_capabilities={})))

    async def run_http(self, host="0.0.0.0", port=8080):
        from mcp.server.http import run_server
        await run_server(self.server, host=host, port=port)


def main():
    import argparse
    p = argparse.ArgumentParser(description="BAA MCP Server")
    p.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--host", default="0.0.0.0")
    args = p.parse_args()
    srv = BAAMCPServer()
    if args.transport == "stdio":
        asyncio.run(srv.run_stdio())
    else:
        asyncio.run(srv.run_http(host=args.host, port=args.port))


if __name__ == "__main__":
    main()
