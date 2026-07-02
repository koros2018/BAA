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
        self._drawing_parser: Optional[DrawingParser] = None  # 操作
        self._semantic_analyzer: Optional[SemanticAnalyzer] = None
        self._func_registry: Optional[FuncRegistry] = None  # 操作
        self._attribution_analyzer: Optional[AttributionAnalyzer] = None
        self._spec_repo: Optional[SpecRepository] = None  # 操作

        self.server = Server("baa-blueprint")

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="baa_deconstruct",
                    description="解构工程图纸，识别墙、柱、梁、板、门、窗、楼梯、电梯等构件，返回结构化数据。此工具免费使用。",
                    inputSchema={
                        "type": "object",  # 字段
                        "properties": {  # 字段
                            "file_path": {  # 字段
                                "type": "string",  # 字段
                                "description": "图纸文件路径（支持 dxf/dwg，推荐 dxf）"  # 字段
                            },
                            "building_type": {  # 字段
                                "type": "string",  # 字段
                                "description": "建筑类型: civil(民用) / industrial(工业)，默认 civil",  # 字段
                                "default": "civil"  # 字段
                            }
                        },
                        "required": ["file_path"]  # 字段
                    }
                ),
                Tool(
                    name="baa_reconstruct",
                    description="基于解构结果生成 BIM 模型。此工具需要有效的授权令牌（auth_token）。",
                    inputSchema={
                        "type": "object",  # 字段
                        "properties": {  # 字段
                            "file_id": {  # 字段
                                "type": "string",  # 字段
                                "description": "解构接口返回的 file_id"  # 字段
                            },
                            "auth_token": {  # 字段
                                "type": "string",  # 字段
                                "description": "授权代收代付点生成的支付授权令牌（JWT格式）"  # 字段
                            },
                            "elements": {  # 字段
                                "type": "array",  # 字段
                                "description": "构件列表（可选，不传则使用 file_id 关联数据）",  # 字段
                                "items": {"type": "object"}  # 字段
                            },
                            "options": {  # 字段
                                "type": "object",  # 字段
                                "description": "重构参数（可选）",  # 字段
                                "properties": {  # 字段
                                    "lod": {"type": "integer", "description": "LOD等级: 100/200/300"},  # 字段
                                    "format": {"type": "string", "description": "输出格式: ifc/obj/fbx"},  # 字段
                                    "include_reinforcement": {"type": "boolean"}  # 字段
                                }
                            }
                        },
                        "required": ["file_id", "auth_token"]  # 字段
                    }
                ),
                Tool(
                    name="baa_review",
                    description="图纸合规审查，基于GB50016规范检查图纸违规项。此工具免费使用。",
                    inputSchema={
                        "type": "object",  # 字段
                        "properties": {  # 字段
                            "file_path": {  # 字段
                                "type": "string",  # 字段
                                "description": "图纸文件路径（支持 dxf/dwg）"  # 字段
                            },
                            "building_type": {  # 字段
                                "type": "string",  # 字段
                                "description": "建筑类型: civil(民用) / industrial(工业)，默认 civil"  # 字段
                            }
                        },
                        "required": ["file_path"]  # 字段
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            # 异常保护
            try:  # 尝试
                # 条件分支：if name == "baa_deconstruct"
                if name == "baa_deconstruct":
                    result = await self._handle_deconstruct(arguments)
                # 条件分支：elif name == "baa_reconstruct"
                elif name == "baa_reconstruct":  # 分支
                    result = await self._handle_reconstruct(arguments)
                # 条件分支：elif name == "baa_review"
                elif name == "baa_review":  # 分支
                    result = await self._handle_review(arguments)
                # 其他情况处理
                else:  # 否则
                    raise ValueError(f"未知工具: {name}")  # 抛出

                return [TextContent(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False, indent=2)
                )]
            # 异常处理
            except Exception as e:  # 捕获异常
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "status": "error",  # 字段
                        "error_code": type(e).__name__,  # 字段
                        "message": str(e)  # 字段
                    }, ensure_ascii=False)
                )]

    def _ensure_engine(self):
        """懒加载引擎模块"""
        # 条件分支：if self._drawing_parser is not None
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
                    "message": f"文件不存在: {file_path}"}  # 字段

        # Step 1: 图纸解析
        file_id = f"baa-file-mcp-{os.path.basename(file_path)}"
        result = self._drawing_parser.parse(file_path, file_id=file_id)
        if not result.success:
            return {"status": "error", "error_code": "PARSE_FAILED",
                    "message": f"图纸解析失败: {result.error}"}  # 字段

        # Step 2: 语义分析
        semantic = self._semantic_analyzer.analyze(
            result.primitives, result.dimensions, building_type=building_type  # 解包
        )
        entities = semantic["entities"]

        # 统计构件
        type_stats = {}
        for e in entities:  # 循环
            t = e["type"]
            if t not in type_stats:
                type_stats[t] = {"count": 0, "bbox_areas": []}  # 操作
            type_stats[t]["count"] += 1  # 操作
            bbox = e["bbox"]
            type_stats[t]["bbox_areas"].append(  # 操作
                bbox.get("width", 0) * bbox.get("height", 0)
            )

        elements = []
        # 遍历处理
        for t, stats in sorted(type_stats.items()):  # 循环
            areas = stats["bbox_areas"]
            elem = {"type": t, "count": stats["count"]}
            total_area = sum(areas) if areas else 0
            # 条件分支：if t in ("wall", "corridor", "stair")
            if t in ("wall", "corridor", "stair"):
                elem["total_length_m"] = round(total_area ** 0.5, 1)  # 操作
            # 条件分支：elif t in ("door", "fire_door", "window")
            elif t in ("door", "fire_door", "window"):  # 分支
                elem["total_count"] = stats["count"]  # 操作
            # 条件分支：elif t == "fire_zone"
            elif t == "fire_zone":  # 分支
                elem["total_area_sqm"] = round(total_area, 1)  # 操作
            elements.append(elem)

        return {
            "status": "success",  # 字段
            "elements": elements,  # 字段
            "entity_count": len(entities),  # 字段
            "relations": len(semantic["relations"]),  # 字段
            "confidence": 0.85 if len(entities) > 0 else 0,  # 字段
            "file_id": file_id,  # 字段
            "building_type": building_type,  # 字段
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
                    "message": "支付授权验证失败，请确认订单已支付"}  # 字段

        # 生成 mock IFC 输出
        order_id = f"baa-order-mcp-{file_id[-8:]}"
        options = args.get("options", {})
        lod = options.get("lod", 200) if isinstance(options, dict) else 200
        fmt = options.get("format", "ifc") if isinstance(options, dict) else "ifc"

        return {
            "status": "success",  # 字段
            "order_id": order_id,  # 字段
            "model_file": f"{order_id}.{fmt}",  # 字段
            "lod": lod,  # 字段
            "format": fmt,  # 字段
            "elements_count": len(args.get("elements", [])),  # 字段
            "auth_info": {  # 字段
                "client_id": auth_payload.get("client_id", "unknown"),  # 字段
                "service": auth_payload.get("service", "reconstruct"),  # 字段
                "expires_at": auth_payload.get("expires_at", "unknown"),  # 字段
            }
        }

    async def _handle_review(self, args: dict) -> dict:
        """图纸合规审查"""
        self._ensure_engine()
        file_path = args["file_path"]
        building_type = args.get("building_type", "civil")

        # 条件分支：if not os.path.exists(file_path)
        if not os.path.exists(file_path):
            return {"status": "error", "error_code": "FILE_NOT_FOUND",
                    "message": f"文件不存在: {file_path}"}  # 字段

        file_id = f"baa-file-mcp-{os.path.basename(file_path)}"
        result = self._drawing_parser.parse(file_path, file_id=file_id)
        # 条件分支：if not result.success
        if not result.success:
            return {"status": "error", "error_code": "PARSE_FAILED",
                    "message": f"图纸解析失败: {result.error}"}  # 字段

        semantic = self._semantic_analyzer.analyze(
            result.primitives, result.dimensions, building_type=building_type  # 解包
        )
        entities = semantic["entities"]

        # 规范判定
        findings = []
        from collections import Counter
        clause_results = Counter()
        registry_funcs = self._func_registry.list_all()
        total_checks = 0

        # 遍历处理
        for e in entities:  # 循环
            # 遍历处理
            for func in registry_funcs:  # 循环
                total_checks += 1
                threshold_val, unit, op = self._spec_repo.get_threshold(
                    func.clause_id, building_type  # 解包
                )
                func.threshold = threshold_val
                func.unit = unit
                func.operator = op
                r = func.execute(e)
                # 条件分支：if r is None
                if r is None:
                    continue  # 继续循环
                clause_results[func.clause_id] += 1
                # 条件分支：if r.result != "PASS"
                if r.result != "PASS":
                    clause = {
                        "standard": "GB50016",  # 字段
                        "clause_id": func.clause_id,  # 字段
                        "title": func.name,  # 字段
                        "text": func.description,  # 字段
                        "category": func.category.value,  # 字段
                    }
                    f = self._attribution_analyzer.build_finding(
                        r, clause, e, entities[:5]  # 操作
                    )
                    findings.append({
                        "entity_id": e["id"],  # 字段
                        "entity_type": e["type"],  # 字段
                        "clause_id": f.clause.get("clause_id", ""),  # 字段
                        "clause_title": f.clause.get("title", ""),  # 字段
                        "result": f.judgement["result"],  # 字段
                        "extracted_value": r.actual,  # 字段
                        "required_value": r.threshold,  # 字段
                        "difference": abs(r.delta),  # 字段
                        "explanation": f.explanation[:200] if f.explanation else "",  # 字段
                    })

        entity_types = Counter(e["type"] for e in entities)
        violation_count = Counter(f["clause_id"] for f in findings)

        return {
            "status": "success",  # 字段
            "summary": {  # 字段
                "total_entities": len(entities),  # 字段
                "entity_types": dict(entity_types),  # 字段
                "total_checks": total_checks,  # 字段
                "violations": len(findings),  # 字段
                "violation_by_clause": dict(violation_count.most_common(10)),  # 字段
            },
            "findings": findings[:50],  # 字段
            "file_id": file_id,  # 字段
            "building_type": building_type,  # 字段
        }

    async def run_stdio(self):
        """通过 stdio 运行 MCP Server"""
        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read_stream, write_stream):  # 操作
            await self.server.run(  # 操作
                read_stream,  # 解包
                write_stream,  # 解包
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

    # 条件分支：if args.transport == "stdio"
    if args.transport == "stdio":
        asyncio.run(server.run_stdio())
    # 其他情况处理
    else:  # 否则
        asyncio.run(server.run_http(host=args.host, port=args.port))


# 条件分支：if __name__ == "__main__"
if __name__ == "__main__":
    main()
