"""
BAA 真实图纸批量验证脚本 v1.12.0

逐张解析 data/ 下的真实 DWG 图纸，执行全流程审查，输出验证报告。

用法:
    python scripts/validate_real_drawings.py [--output report.json]

输出:
    - stdout: 每张图纸的概要结果
    - report.json: 完整的结构化验证报告
"""
import sys, os, json, time, argparse, re
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.semantic_analyzer import SemanticAnalyzer
from src.baa_engine.atomic_functions import FuncRegistry
from src.baa_engine.spec_repository import SpecRepository
from src.baa_engine.attribution_analyzer import AttributionAnalyzer

# ── 图纸列表 ────────────────────────────────────────────
# (文件名, 标签, 建筑类型推断)
DRAWINGS = [
    ("基础+2#,3#上部-202104", "基础+上部结构", "civil"),
    ("E-00-01-01 室外电气总平面图", "室外电气总平面", "civil"),
    ("20210409-3#泵房_t3", "3#泵房", "industrial"),
    ("202109409-2#配电房_t3", "2#配电房", "industrial"),
    ("A1IDC及通信机楼结构平面图20161227z", "IDC通信机楼结构", "industrial"),
    ("A1云计算中心_水消防2017.03.31_t3", "云计算中心水消防", "industrial"),
    ("A1云计算中心平面图0405_t3", "云计算中心平面", "industrial"),
    ("ZY项目1#数据中心机房平立剖面图_t7_t3", "数据中心机房", "industrial"),
    ("中原人工智能计算中心总图-0409_t3", "AI计算中心总图", "industrial"),
    ("E-00-11-01电力配电箱系统图", "电力配电箱系统", "industrial"),
]


def _resolve_filepath(data_dir: Path, name: str) -> Path:
    """优先尝试 .dxf，不存在则用 .dwg"""
    dxf_path = data_dir / f"{name}.dxf"
    if dxf_path.exists():
        return dxf_path
    dwg_path = data_dir / f"{name}.dwg"
    if dwg_path.exists():
        return dwg_path
    return dxf_path  # 返回 DXF 路径（方便上层报错）


def validate_drawing(data_dir: Path, filename: str, label: str, btype: str) -> dict:
    """对单张真实图纸执行解析→审查全流程，返回结构化结果"""
    filepath = _resolve_filepath(data_dir, filename)
    if not filepath.exists():
        return {"file": filename, "label": label, "building_type": btype,
                "status": "error", "error": "文件不存在"}

    t0 = time.time()
    result = {
        "file": filename,
        "label": label,
        "building_type": btype,
        "status": "unknown",
        "parse_time_ms": 0,
        "entity_count": 0,
        "element_count": 0,
        "violations": [],
        "violation_count": 0,
        "violations_by_type": {},
        "violations_by_severity": {},
        "funcs_fired": set(),
        "funcs_matched": set(),
    }

    try:
        # 1. 解析
        parser = DrawingParser()
        drawing_result = parser.parse(str(filepath))
        t_parse = time.time()
        result["parse_time_ms"] = int((t_parse - t0) * 1000)
        result["element_count"] = len(drawing_result.primitives)

        if not drawing_result.primitives:
            result["status"] = "empty"
            result["error"] = "解析后无图元"
            result["total_time_ms"] = int((time.time() - t0) * 1000)
            return result

        # 2. 语义分析
        analyzer = SemanticAnalyzer()
        semantic = analyzer.analyze(drawing_result.primitives, drawing_result.dimensions)
        entities = semantic.get("entities", semantic) if isinstance(semantic, dict) else semantic
        # 兼容：analyze 可能返回 dict {entities, relations, attributes} 或直接返回列表
        if isinstance(entities, dict):
            entities = entities.get("entities", [])
        result["entity_count"] = len(entities)
        entity_types = Counter(e.get("type", "unknown") for e in entities if isinstance(e, dict))
        result["entity_types"] = dict(entity_types)

        # 3. 原子函数判定
        registry = FuncRegistry()
        funcs_matched = set()
        all_results = []

        dict_entities = [e for e in entities if isinstance(e, dict)]
        for entity in dict_entities:
            for func in registry.list_all():
                if func.matches(entity):
                    funcs_matched.add(func.func_id)
                    r = func.execute(entity)
                    if r and r.result == "FAIL":
                        all_results.append(r)

        # 缺失检查：对未匹配到的实体类型做存在性检查
        for func in registry.list_all():
            if func.category.name == "EXIST":
                has_match = any(func.matches(e) for e in dict_entities)
                if not has_match:
                    r = func.execute(None)
                    if r and r.result == "FAIL":
                        all_results.append(r)

        result["funcs_matched"] = sorted(funcs_matched)

        # 4. 归因分析
        attributor = AttributionAnalyzer()
        spec_repo = SpecRepository()
        dict_entities = [e for e in entities if isinstance(e, dict)]
        findings = []
        for r in all_results:
            clause = spec_repo.get(r.clause_id)
            clause_dict = clause.__dict__ if clause else {}
            entity_info = {}
            if r.entity_id:
                for e in dict_entities:
                    if e.get("id") == r.entity_id:
                        entity_info = e
                        break
            f = attributor.build_finding(r, clause_dict, entity_info, [])
            fd = f.__dict__ if hasattr(f, '__dict__') else {}
            # 从嵌套结构中提取字段
            judgement = fd.get("judgement", {})
            clause_data = fd.get("clause", {})
            extracted = fd.get("extracted_params", {})
            findings.append({
                "finding_id": fd.get("finding_id", ""),
                "func_id": r.func_id,
                "clause_id": clause_data.get("clause_id", r.clause_id),
                "clause_title": clause_data.get("title", ""),
                "entity_type": extracted.get("entity_type", ""),
                "entity_id": extracted.get("entity_id", ""),
                "severity": judgement.get("severity", r.severity.name.lower()),
                "result": judgement.get("result", r.result),
                "actual": judgement.get("actual", 0),
                "threshold": judgement.get("threshold", 0),
                "operator": judgement.get("operator", ""),
                "delta": judgement.get("delta", 0),
                "explanation": fd.get("explanation", ""),
                "suggestion": fd.get("suggestion", ""),
            })
            result["funcs_fired"].add(r.func_id)

        result["funcs_fired"] = sorted(result["funcs_fired"])
        result["violations"] = findings
        result["violation_count"] = len(findings)

        # 按类型/严重度统计
        type_counter = Counter()
        sev_counter = Counter()
        for f in findings:
            type_counter[f.get("clause_id", "unknown")] += 1
            sev_counter[f.get("severity", "unknown")] += 1
        result["violations_by_type"] = dict(type_counter)
        result["violations_by_severity"] = dict(sev_counter)

        result["status"] = "ok" if result["element_count"] > 0 else "empty"
        result["total_time_ms"] = int((time.time() - t0) * 1000)

    except Exception as e:
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {str(e)}"
        result["total_time_ms"] = int((time.time() - t0) * 1000)

    return result


def print_summary(results: list):
    """打印人类可读的汇总表"""
    print(f"\n{'='*80}")
    print(f"  BAA 真实图纸批量验证报告")
    print(f"  v1.12.0 | 原子函数 30/30 | 规范 31条 | {len(results)} 张图纸")
    print(f"{'='*80}\n")

    header = f"{'#':<3} {'图纸名称':<28} {'类型':<10} {'图元':<6} {'实体':<6} {'违规':<6} {'严重':<6} {'主要':<6} {'轻微':<6} {'耗时(ms)':<10} {'状态':<10}"
    print(header)
    print("-" * len(header))

    total_elements = 0
    total_entities = 0
    total_violations = 0
    ok_count = 0
    error_count = 0

    for i, r in enumerate(results):
        sev = r.get("violations_by_severity", {})
        is_ok = r["status"] == "ok"
        if is_ok:
            ok_count += 1
        else:
            error_count += 1
        total_elements += r["element_count"]
        total_entities += r["entity_count"]
        total_violations += r["violation_count"]

        print(f"{i+1:<3} {r['label']:<28} {r['building_type']:<10} "
              f"{r['element_count']:<6} {r['entity_count']:<6} "
              f"{r['violation_count']:<6} {sev.get('critical', 0):<6} "
              f"{sev.get('major', 0):<6} {sev.get('minor', 0):<6} "
              f"{r.get('total_time_ms', 0):<10} {'✅' if is_ok else '❌'}")

    print("-" * len(header))
    print(f"{'合计':<3} {'':<28} {'':<10} "
          f"{total_elements:<6} {total_entities:<6} "
          f"{total_violations:<6} {'':<18} "
          f"{ok_count}/{ok_count+error_count}")
    print()


def print_detail(results: list):
    """打印每张图纸的违规详情"""
    for r in results:
        if r["status"] != "ok":
            print(f"\n  ❌ {r['label']}: {r.get('error', '未知错误')}")
            continue
        print(f"\n  📐 {r['label']} ({r['building_type']})")
        print(f"     图元: {r['element_count']} → 实体: {r['entity_count']}")
        print(f"     违规: {r['violation_count']} 项 "
              f"(严重: {r['violations_by_severity'].get('critical',0)}, "
              f"主要: {r['violations_by_severity'].get('major',0)}, "
              f"轻微: {r['violations_by_severity'].get('minor',0)})")
        print(f"     命中函数: {', '.join(r['funcs_fired'][:10])}")
        if r.get("entity_types"):
            et = sorted(r["entity_types"].items(), key=lambda x: -x[1])[:8]
            print(f"     实体分布: {', '.join(f'{k}={v}' for k,v in et)}")

        if r["violations"]:
            for v in r["violations"][:5]:
                sev_icon = {'critical': '🔴', 'major': '🟠', 'minor': '🟡'}
                sev = v.get("severity", "")
                expl = v.get("explanation", v.get("clause_id", ""))[:100]
                print(f"       {sev_icon.get(sev, '⚪')} [{sev}] {expl}")
            if len(r["violations"]) > 5:
                print(f"       ... 还有 {len(r['violations'])-5} 项")


def main():
    parser = argparse.ArgumentParser(description="BAA 真实图纸批量验证")
    parser.add_argument("--output", "-o", default="", help="输出JSON报告路径")
    parser.add_argument("--detail", "-d", action="store_true", help="打印违规详情")
    args = parser.parse_args()

    data_dir = Path(__file__).resolve().parent.parent / "data"

    print(f"\n  正在验证 {len(DRAWINGS)} 张真实图纸...")
    results = []
    for i, (filename, label, btype) in enumerate(DRAWINGS):
        print(f"  [{i+1}/{len(DRAWINGS)}] {label}... ", end="", flush=True)
        r = validate_drawing(data_dir, filename, label, btype)
        status = "✅" if r["status"] == "ok" else "❌"
        print(f"{status} ({r['violation_count']} violations, {r.get('total_time_ms',0)}ms)")
        results.append(r)

    print_summary(results)

    if args.detail:
        print_detail(results)

    # 输出 JSON
    if args.output:
        outpath = Path(args.output)
        # 清理违规详情（减少文件体积）
        for r in results:
            if len(r.get("violations", [])) > 100:
                r["violations"] = r["violations"][:100]
        with open(outpath, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"  报告已写入: {outpath.resolve()}")

    # 返回状态码
    return 0 if all(r["status"] == "ok" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
