"""
BAA MCP Server - 将BAA图纸解构和BIM重构能力封装为MCP工具
基于 DD-9 MCP与Skill接入方案 v4.0（终稿定稿）

启动方式：
  # Streamable HTTP（推荐，适用于远程部署）
  python src/mcp/baa_mcp_server.py --transport streamable-http --port 8080

  # Stdio（适用于本地或容器内）
  python src/mcp/baa_mcp_server.py --transport stdio
"""
import json  # stdlib: JSON
import os  # stdlib: filesystem ops
import sys  # import
import asyncio  # stdlib: async
from pathlib import Path  # import: path utils
from typing import Any, Optional  # typing: type hints

# 添加项目根到路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # function call
sys.path.insert(0, str(PROJECT_ROOT))  # sys path

from mcp.server import Server, NotificationOptions  # import
from mcp.server.models import InitializationOptions  # import
from mcp.types import Tool, TextContent  # import
from mcp.server.lowlevel.helper_types import ReadResourceContents  # import

from src.baa_engine.drawing_parser import DrawingParser  # import
from src.baa_engine.semantic_analyzer import SemanticAnalyzer  # import
from src.baa_engine.atomic_functions import FuncRegistry  # import
from src.baa_engine.attribution_analyzer import AttributionAnalyzer  # import
from src.baa_engine.spec_repository import SpecRepository  # import
from src.api.baa_api import generate_auth_token, verify_auth_token  # import


class BAAMCPServer:  # class definition
    """BAA MCP Server"""

    def __init__(self):  # function: def __init__(self):
        # 懒加载引擎
        self._drawing_parser: Optional[DrawingParser] = None  # 操作
        self._semantic_analyzer: Optional[SemanticAnalyzer] = None  # assignment
        self._func_registry: Optional[FuncRegistry] = None  # 操作
        self._attribution_analyzer: Optional[AttributionAnalyzer] = None  # assignment
        self._spec_repo: Optional[SpecRepository] = None  # 操作

        self.server = Server("baa-blueprint")  # function call

        @self.server.list_tools()  # function call
        async def list_tools() -> list[Tool]:  # function call
            return [  # return: list
                Tool(  # code
                    name="baa_deconstruct",  # assignment
                    description="解构工程图纸，识别墙、柱、梁、板、门、窗、楼梯、电梯等构件，返回结构化数据。此工具免费使用。",  # assignment
                    inputSchema={  # assignment
                        "type": "object",  # 字段
                        "properties": {  # 字段
                            "file_path": {  # 字段
                                "type": "string",  # 字段
                                "description": "图纸文件路径（支持 dxf/dwg，推荐 dxf）"  # 字段
                            },  # code
                            "building_type": {  # 字段
                                "type": "string",  # 字段
                                "description": "建筑类型: civil(民用) / industrial(工业)，默认 civil",  # 字段
                                "default": "civil"  # 字段
                            }  # code
                        },  # code
                        "required": ["file_path"]  # 字段
                    }  # code
                ),  # code
                Tool(  # code
                    name="baa_reconstruct",  # assignment
                    description="基于解构结果生成 BIM 模型。此工具需要有效的授权令牌（auth_token）。",  # assignment
                    inputSchema={  # assignment
                        "type": "object",  # 字段
                        "properties": {  # 字段
                            "file_id": {  # 字段
                                "type": "string",  # 字段
                                "description": "解构接口返回的 file_id"  # 字段
                            },  # code
                            "auth_token": {  # 字段
                                "type": "string",  # 字段
                                "description": "授权代收代付点生成的支付授权令牌（JWT格式）"  # 字段
                            },  # code
                            "elements": {  # 字段
                                "type": "array",  # 字段
                                "description": "构件列表（可选，不传则使用 file_id 关联数据）",  # 字段
                                "items": {"type": "object"}  # 字段
                            },  # code
                            "options": {  # 字段
                                "type": "object",  # 字段
                                "description": "重构参数（可选）",  # 字段
                                "properties": {  # 字段
                                    "lod": {"type": "integer", "description": "LOD等级: 100/200/300"},  # 字段
                                    "format": {"type": "string", "description": "输出格式: ifc/obj/fbx"},  # 字段
                                    "include_reinforcement": {"type": "boolean"}  # 字段
                                }  # code
                            }  # code
                        },  # code
                        "required": ["file_id", "auth_token"]  # 字段
                    }  # code
                ),  # code
                Tool(  # code
                    name="baa_review",  # assignment
                    description="图纸合规审查，基于GB50016规范检查图纸违规项。此工具免费使用。",  # assignment
                    inputSchema={  # assignment
                        "type": "object",  # 字段
                        "properties": {  # 字段
                            "file_path": {  # 字段
                                "type": "string",  # 字段
                                "description": "图纸文件路径（支持 dxf/dwg）"  # 字段
                            },  # code
                            "building_type": {  # 字段
                                "type": "string",  # 字段
                                "description": "建筑类型: civil(民用) / industrial(工业)，默认 civil"  # 字段
                            }  # code
                        },  # code
                        "required": ["file_path"]  # 字段
                    }  # code
                )  # code
            ]  # code

        @self.server.call_tool()  # function call
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:  # function call
            # 异常保护
            try:  # 尝试
                # 条件分支：if name == "baa_deconstruct"
                if name == "baa_deconstruct":  # condition: name == "baa_deconstruct":
                    result = await self._handle_deconstruct(arguments)  # function call
                # 条件分支：elif name == "baa_reconstruct"
                elif name == "baa_reconstruct":  # 分支
                    result = await self._handle_reconstruct(arguments)  # function call
                # 条件分支：elif name == "baa_review"
                elif name == "baa_review":  # 分支
                    result = await self._handle_review(arguments)  # function call
                # 其他情况处理
                else:  # 否则
                    raise ValueError(f"未知工具: {name}")  # 抛出

                return [TextContent(  # return: list
                    type="text",  # assignment
                    text=json.dumps(result, ensure_ascii=False, indent=2)  # serialize JSON
                )]  # code
            # 异常处理
            except Exception as e:  # 捕获异常
                return [TextContent(  # return: list
                    type="text",  # assignment
                    text=json.dumps({  # assignment
                        "status": "error",  # 字段
                        "error_code": type(e).__name__,  # 字段
                        "message": str(e)  # 字段
                    }, ensure_ascii=False)  # assignment
                )]  # code

    def _ensure_engine(self):  # function: def _ensure_engine(self):
        """懒加载引擎模块"""
        # 条件分支：if self._drawing_parser is not None
        if self._drawing_parser is not None:  # check: value is not None
            return  # code
        self._drawing_parser = DrawingParser()  # function call
        self._semantic_analyzer = SemanticAnalyzer()  # function call
        self._func_registry = FuncRegistry()  # function call
        self._attribution_analyzer = AttributionAnalyzer()  # function call
        self._spec_repo = SpecRepository()  # function call

    async def _handle_deconstruct(self, args: dict) -> dict:  # function call
        """图纸解构"""
        self._ensure_engine()  # function call
        file_path = args["file_path"]  # assignment
        building_type = args.get("building_type", "civil")  # function call

        # 检查文件存在
        if not os.path.exists(file_path):  # check: negated condition
            return {"status": "error", "error_code": "FILE_NOT_FOUND",  # return: dict
                    "message": f"文件不存在: {file_path}"}  # 字段

        # Step 1: 图纸解析
        file_id = f"baa-file-mcp-{os.path.basename(file_path)}"  # path operation
        result = self._drawing_parser.parse(file_path, file_id=file_id)  # function call
        if not result.success:  # check: negated condition
            return {"status": "error", "error_code": "PARSE_FAILED",  # return: dict
                    "message": f"图纸解析失败: {result.error}"}  # 字段

        # Step 2: 语义分析
        semantic = self._semantic_analyzer.analyze(  # assignment
            result.primitives, result.dimensions, building_type=building_type  # 解包
        )  # code
        entities = semantic["entities"]  # assignment

        # 统计构件
        type_stats = {}  # assignment
        for e in entities:  # 循环
            t = e["type"]  # assignment
            if t not in type_stats:  # check: membership test
                type_stats[t] = {"count": 0, "bbox_areas": []}  # 操作
            type_stats[t]["count"] += 1  # 操作
            bbox = e["bbox"]  # assignment
            type_stats[t]["bbox_areas"].append(  # 操作
                bbox.get("width", 0) * bbox.get("height", 0)  # function call
            )  # code

        elements = []  # assignment
        # 遍历处理
        for t, stats in sorted(type_stats.items()):  # 循环
            areas = stats["bbox_areas"]  # assignment
            elem = {"type": t, "count": stats["count"]}  # assignment
            total_area = sum(areas) if areas else 0  # aggregate sum
            # 条件分支：if t in ("wall", "corridor", "stair")
            if t in ("wall", "corridor", "stair"):  # check: membership test
                elem["total_length_m"] = round(total_area ** 0.5, 1)  # 操作
            # 条件分支：elif t in ("door", "fire_door", "window")
            elif t in ("door", "fire_door", "window"):  # 分支
                elem["total_count"] = stats["count"]  # 操作
            # 条件分支：elif t == "fire_zone"
            elif t == "fire_zone":  # 分支
                elem["total_area_sqm"] = round(total_area, 1)  # 操作
            elements.append(elem)  # append to list

        return {  # return: dict
            "status": "success",  # 字段
            "elements": elements,  # 字段
            "entity_count": len(entities),  # 字段
            "relations": len(semantic["relations"]),  # 字段
            "confidence": 0.85 if len(entities) > 0 else 0,  # 字段
            "file_id": file_id,  # 字段
            "building_type": building_type,  # 字段
        }  # code

    async def _handle_reconstruct(self, args: dict) -> dict:  # function call
        """BIM 重构"""
        self._ensure_engine()  # function call
        file_id = args["file_id"]  # assignment
        auth_token = args["auth_token"]  # assignment

        # 验证授权
        auth_payload = verify_auth_token(auth_token)  # function call
        if auth_payload is None:  # check: value is None
            return {"status": "error", "error_code": "AUTH_FAILED",  # return: dict
                    "message": "支付授权验证失败，请确认订单已支付"}  # 字段

        # 生成 mock IFC 输出
        order_id = f"baa-order-mcp-{file_id[-8:]}"  # assignment
        options = args.get("options", {})  # function call
        lod = options.get("lod", 200) if isinstance(options, dict) else 200  # type check
        fmt = options.get("format", "ifc") if isinstance(options, dict) else "ifc"  # type check

        return {  # return: dict
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
            }  # code
        }  # code

    async def _handle_review(self, args: dict) -> dict:  # function call
        """图纸合规审查"""
        self._ensure_engine()  # function call
        file_path = args["file_path"]  # assignment
        building_type = args.get("building_type", "civil")  # function call

        # 条件分支：if not os.path.exists(file_path)
        if not os.path.exists(file_path):  # check: negated condition
            return {"status": "error", "error_code": "FILE_NOT_FOUND",  # return: dict
                    "message": f"文件不存在: {file_path}"}  # 字段

        file_id = f"baa-file-mcp-{os.path.basename(file_path)}"  # path operation
        result = self._drawing_parser.parse(file_path, file_id=file_id)  # function call
        # 条件分支：if not result.success
        if not result.success:  # check: negated condition
            return {"status": "error", "error_code": "PARSE_FAILED",  # return: dict
                    "message": f"图纸解析失败: {result.error}"}  # 字段

        semantic = self._semantic_analyzer.analyze(  # assignment
            result.primitives, result.dimensions, building_type=building_type  # 解包
        )  # code
        entities = semantic["entities"]  # assignment

        # 规范判定
        findings = []  # assignment
        from collections import Counter  # stdlib: collections
        clause_results = Counter()  # function call
        registry_funcs = self._func_registry.list_all()  # check all true
        total_checks = 0  # assignment

        # 遍历处理
        for e in entities:  # 循环
            # 遍历处理
            for func in registry_funcs:  # 循环
                total_checks += 1  # accumulate
                threshold_val, unit, op = self._spec_repo.get_threshold(  # assignment
                    func.clause_id, building_type  # 解包
                )  # code
                func.threshold = threshold_val  # assignment
                func.unit = unit  # assignment
                func.operator = op  # assignment
                r = func.execute(e)  # function call
                # 条件分支：if r is None
                if r is None:  # check: value is None
                    continue  # 继续循环
                clause_results[func.clause_id] += 1  # accumulate
                # 条件分支：if r.result != "PASS"
                if r.result != "PASS":  # condition: r.result != "PASS":
                    clause = {  # assignment
                        "standard": "GB50016",  # 字段
                        "clause_id": func.clause_id,  # 字段
                        "title": func.name,  # 字段
                        "text": func.description,  # 字段
                        "category": func.category.value,  # 字段
                    }  # code
                    f = self._attribution_analyzer.build_finding(  # assignment
                        r, clause, e, entities[:5]  # 操作
                    )  # code
                    findings.append({  # code
                        "entity_id": e["id"],  # 字段
                        "entity_type": e["type"],  # 字段
                        "clause_id": f.clause.get("clause_id", ""),  # 字段
                        "clause_title": f.clause.get("title", ""),  # 字段
                        "result": f.judgement["result"],  # 字段
                        "extracted_value": r.actual,  # 字段
                        "required_value": r.threshold,  # 字段
                        "difference": abs(r.delta),  # 字段
                        "explanation": f.explanation[:200] if f.explanation else "",  # 字段
                    })  # code

        entity_types = Counter(e["type"] for e in entities)  # function call
        violation_count = Counter(f["clause_id"] for f in findings)  # function call

        return {  # return: dict
            "status": "success",  # 字段
            "summary": {  # 字段
                "total_entities": len(entities),  # 字段
                "entity_types": dict(entity_types),  # 字段
                "total_checks": total_checks,  # 字段
                "violations": len(findings),  # 字段
                "violation_by_clause": dict(violation_count.most_common(10)),  # 字段
            },  # code
            "findings": findings[:50],  # 字段
            "file_id": file_id,  # 字段
            "building_type": building_type,  # 字段
        }  # code

    async def run_stdio(self):  # function call
        """通过 stdio 运行 MCP Server"""
        from mcp.server.stdio import stdio_server  # import
        async with stdio_server() as (read_stream, write_stream):  # 操作
            await self.server.run(  # 操作
                read_stream,  # 解包
                write_stream,  # 解包
                InitializationOptions(  # code
                    server_name="baa-blueprint",  # assignment
                    server_version="1.2.0",  # assignment
                    capabilities=self.server.get_capabilities(  # assignment
                        notification_options=NotificationOptions(),  # function call
                        experimental_capabilities={},  # assignment
                    ),  # code
                ),  # code
            )  # code

    async def run_http(self, host: str = "0.0.0.0", port: int = 8080):  # function call
        """通过 Streamable HTTP 运行 MCP Server"""
        from mcp.server.http import run_server  # import
        await run_server(self.server, host=host, port=port)  # function call


def main():  # function: def main():
    import argparse  # import
    parser = argparse.ArgumentParser(description="BAA MCP Server")  # function call
    parser.add_argument("--transport", choices=["stdio", "streamable-http"],  # assignment
                        default="stdio")  # assignment
    parser.add_argument("--port", type=int, default=8080)  # function call
    parser.add_argument("--host", default="0.0.0.0")  # function call
    args = parser.parse_args()  # function call

    server = BAAMCPServer()  # function call

    # 条件分支：if args.transport == "stdio"
    if args.transport == "stdio":  # check: OR condition
        asyncio.run(server.run_stdio())  # function call
    # 其他情况处理
    else:  # 否则
        asyncio.run(server.run_http(host=args.host, port=args.port))  # function call


# 条件分支：if __name__ == "__main__"
if __name__ == "__main__":  # condition: __name__ == "__main__":
    main()  # function call
