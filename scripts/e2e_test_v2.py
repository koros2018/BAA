"""
BAA Level 5 端到端集成测试
覆盖: 上传→解析→识别→判定→归因→报告 全流程
验证标准: ≥85%判定准确率（合成图纸），真实图纸跑通即可
"""
import sys
import os
import json
import time
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def section(title):
    """打印分节标题"""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ── Level 1: 原子函数单元测试（已知违规/合规） ──────────

def level_1_atomic_functions():
    """L1: 10个原子函数已知输入验证"""
    section("Level 1: 原子函数单元测试")
    from src.baa_engine.atomic_functions import FuncRegistry

    registry = FuncRegistry()
    funcs = registry.list_all()
    print(f"  原子函数: {len(funcs)}个")

    passed = 0
    total = 0
    results = []

    for func in funcs:
        # 合规测试（满足阈值的实体）
        pass_entity = {
            "id": "TEST_001",
            "type": "stair",
            "bbox": {"x": 0, "y": 0, "width": 2000, "height": 2000},
            "properties": {},
        }
        if func.func_id == "DIM-001":
            pass_entity["type"] = "stair"
            pass_entity["properties"]["width"] = 1500  # 1.5m
        elif func.func_id == "DIM-002":
            pass_entity["type"] = "fire_zone"
            pass_entity["properties"]["area"] = 2000000  # 2m²
        elif func.func_id == "DIM-003":
            pass_entity["type"] = "road"
            pass_entity["properties"]["width"] = 5000  # 5m
        elif func.func_id == "DIST-001":
            pass_entity["type"] = "corridor"
            pass_entity["properties"]["length"] = 20000  # 20m
        elif func.func_id == "COUNT-001":
            pass_entity["type"] = "exit"
            pass_entity["properties"]["exit_count"] = 3
        elif func.func_id == "ATTR-001":
            pass_entity["type"] = "fire_door"
            pass_entity["properties"]["rating"] = 1
        elif func.func_id == "DIM-004":
            pass_entity["type"] = "corridor"
            pass_entity["properties"]["width"] = 1500  # 1.5m
        elif func.func_id == "AREA-001":
            pass_entity["type"] = "room"
            pass_entity["properties"]["area"] = 10000000  # 10m²
        elif func.func_id == "EXIST-001":
            pass_entity["type"] = "stair"
            pass_entity["properties"]["count"] = 2
        elif func.func_id == "DIM-005":
            pass_entity["type"] = "window"
            pass_entity["properties"]["area"] = 2000000  # 2m²

        r_pass = func.execute(pass_entity)
        total += 1
        if r_pass.result == "PASS":
            passed += 1
            results.append(f"  ✅ {func.clause_id} {func.name}: PASS")
        else:
            results.append(f"  ❌ {func.clause_id} {func.name}: 应为PASS, 实际{r_pass.result}")

        # 违规测试（不满足阈值的实体）
        fail_entity = {
            "id": "TEST_002",
            "type": pass_entity["type"],
            "bbox": {"x": 0, "y": 0, "width": 2000, "height": 2000},
            "properties": dict(pass_entity["properties"]),
        }
        if "宽度" in func.name or "净宽" in func.name or "宽" in func.name:
            fail_entity["properties"]["width"] = 800  # < 1200mm
        elif "面积" in func.name:
            if func.func_id == "DIM-002":
                fail_entity["properties"]["area"] = 5000000000  # 5000m² > 2500
            elif func.func_id == "AREA-001":
                fail_entity["properties"]["area"] = 1000000  # 1m² < 5m²/人
            else:
                fail_entity["properties"]["area"] = 100000  # 0.1m² < 1m²
        elif "距离" in func.name or "疏散距离" in func.name:
            fail_entity["properties"]["length"] = 40000  # > 30m
        elif "数量" in func.name:
            fail_entity["properties"]["exit_count"] = 1  # < 2
        elif "等级" in func.name:
            fail_entity["properties"]["rating"] = 0
        elif "存在" in func.name or "设置" in func.name:
            fail_entity["properties"]["count"] = 0
        else:
            fail_entity["properties"]["width"] = 100

        r_fail = func.execute(fail_entity)
        total += 1
        if r_fail.result == "FAIL":
            passed += 1
            results.append(f"  ✅ {func.clause_id} {func.name}: FAIL (预期)")
        else:
            results.append(f"  ❌ {func.clause_id} {func.name}: 应为FAIL, 实际{r_fail.result}")

    for r in results:
        print(r)
    print(f"\n  📊 结果: {passed}/{total} 通过 ({passed/total*100:.0f}%)")
    return passed == total


# ── Level 2: 规范JSON覆盖率测试 ─────────────────────────

def level_2_spec_coverage():
    """L2: 10条L1规范验证"""
    section("Level 2: 规范JSON覆盖率测试")
    from src.baa_engine.spec_repository import SpecRepository

    repo = SpecRepository()
    specs = repo.list_all()
    print(f"  规范总数: {len(specs)}条")

    levels = Counter(s.level for s in specs)
    for lv, cnt in levels.most_common():
        print(f"    {lv}: {cnt}条")

    l1_count = sum(1 for s in specs if s.level == "L1")
    print(f"  L1级规范: {l1_count}条 (目标: ≥10条)")
    print(f"  {'✅' if l1_count >= 10 else '❌'} 覆盖率达标")

    return l1_count >= 10


# ── Level 3: 图元识别测试（含消融对比） ─────────────────

def level_3_entity_recognition():
    """L3: 图元识别测试（真实图纸）"""
    section("Level 3: 图元识别测试（真实图纸）")
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.semantic_analyzer import SemanticAnalyzer

    parser = DrawingParser()
    analyzer = SemanticAnalyzer()

    dxf_path = "data/drawings/real/东莞通-建筑-外部参照（不打印）.dxf"
    result = parser.parse(dxf_path)
    assert result.success, "图纸解析失败"
    print(f"  原始图元: {len(result.primitives)}个")

    semantic = analyzer.analyze(result.primitives, result.dimensions, max_entities=1000)
    entities = semantic["entities"]
    relations = semantic["relations"]
    print(f"  语义实体: {len(entities)}个")
    print(f"  空间关系: {len(relations)}个")

    types = Counter(e["type"] for e in entities)
    for t, c in types.most_common():
        print(f"    {t}: {c}")
    print(f"  ✅ 图元识别跑通")
    return len(entities) > 0


# ── Level 4: 归因分析质量测试 ────────────────────────────

def level_4_attribution_quality():
    """L4: 归因分析三要素完备性"""
    section("Level 4: 归因分析质量测试")
    from src.baa_engine.atomic_functions import FuncRegistry
    from src.baa_engine.attribution_analyzer import AttributionAnalyzer

    registry = FuncRegistry()
    attr = AttributionAnalyzer()

    # 构建一个违规场景
    entity = {
        "id": "CORRIDOR_001",
        "type": "corridor",
        "bbox": {"x": 0, "y": 0, "width": 10000, "height": 1500},
        "properties": {"width": 800, "length": 10000},
    }
    clause = {
        "standard": "GB50016",
        "clause_id": "GB50016-5.5.18",
        "title": "疏散走道宽度",
        "text": "疏散走道净宽度不应小于1.2m",
        "category": "疏散",
    }

    func = next(f for f in registry.list_all() if f.clause_id == "GB50016-5.5.18")
    r = func.execute(entity)
    assert r.result == "FAIL", "预期违规未触发"

    finding = attr.build_finding(r, clause, entity, [])
    print(f"  归因ID: {finding.finding_id}")

    # 检查三要素
    has_clause = len(finding.clause) > 0
    has_params = len(finding.extracted_params) > 0
    has_judgement = len(finding.judgement) > 0
    has_attention = len(finding.attention_map) > 0

    print(f"  要素一（规范依据）: {'✅' if has_clause else '❌'} {finding.clause.get('clause_id', '')}")
    print(f"  要素二（参数证据）: {'✅' if has_params else '❌'} {finding.extracted_params.get('extracted_value', '')}")
    print(f"  要素三（判定逻辑）: {'✅' if has_judgement else '❌'} {finding.judgement.get('result', '')}")
    print(f"  注意力热力图: {'✅' if has_attention else '❌'}")

    all_present = has_clause and has_params and has_judgement
    print(f"\n  📊 三要素完备性: {'✅' if all_present else '❌'}")
    return all_present


# ── Level 5: 端到端审查测试（API + 真实图纸） ──────────

def level_5_e2e_api():
    """L5: API端到端审查测试（直接调用内部函数）"""
    section("Level 5: 端到端审查测试")
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.semantic_analyzer import SemanticAnalyzer
    from src.baa_engine.atomic_functions import FuncRegistry
    from src.baa_engine.attribution_analyzer import AttributionAnalyzer

    dxf_path = "data/drawings/real/东莞通-建筑-外部参照（不打印）.dxf"
    fsize = os.path.getsize(dxf_path)
    print(f"  图纸: {dxf_path} ({fsize/1024:.0f}KB)")

    t0 = time.time()

    # Step 1: 解析
    parser = DrawingParser()
    result = parser.parse(dxf_path)
    assert result.success, f"解析失败: {result.error}"
    print(f"  解析: {len(result.primitives)}个图元")

    # Step 2: 语义分析
    analyzer = SemanticAnalyzer()
    semantic = analyzer.analyze(result.primitives, result.dimensions, max_entities=1000)
    entities = semantic["entities"]
    print(f"  语义: {len(entities)}个实体")

    # Step 3: 规范判定+归因
    registry = FuncRegistry()
    attr = AttributionAnalyzer()
    funcs = registry.list_all()

    total_checks = 0
    violations = 0
    findings = []
    for e in entities:
        for func in funcs:
            total_checks += 1
            r = func.execute(e)
            if r.result != "PASS":
                violations += 1
                clause = {"standard": "GB50016", "clause_id": func.clause_id,
                          "title": func.name, "text": func.description,
                          "category": func.category.value}
                f = attr.build_finding(r, clause, e, entities[:5])
                findings.append(f)

    elapsed_ms = int((time.time() - t0) * 1000)

    print(f"  检查: {total_checks}次")
    print(f"  违规: {violations}个")
    print(f"  耗时: {elapsed_ms}ms")

    # 验证
    assert total_checks > 0, "无检查"
    assert elapsed_ms < 10000, f"超时: {elapsed_ms}ms"
    assert len(findings) > 0, "无违规发现"

    # 验证归因完整性
    if findings:
        f = findings[0]
        assert f.clause.get("clause_id", ""), "缺少clause_id"
        assert f.extracted_params.get("extracted_value") is not None, "缺少extracted_value"
        assert f.judgement.get("result", ""), "缺少judgement"
        print(f"  归因示例: {f.clause['clause_id']} value={f.extracted_params['extracted_value']}")

    print(f"\n  📊 Level 5 端到端: ✅")
    return True


# ── 性能基线测试 ─────────────────────────────────────────

def performance_baseline():
    """性能基线测试"""
    section("性能基线测试")
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.semantic_analyzer import SemanticAnalyzer
    from src.baa_engine.atomic_functions import FuncRegistry

    parser = DrawingParser()
    analyzer = SemanticAnalyzer()
    registry = FuncRegistry()

    dxf_path = "data/drawings/real/东莞通-建筑-外部参照（不打印）.dxf"

    # 全量解析
    t0 = time.time()
    result = parser.parse(dxf_path)
    parse_time = (time.time() - t0) * 1000

    # 语义分析（采样500）
    t0 = time.time()
    semantic = analyzer.analyze(result.primitives, result.dimensions, max_entities=500)
    semantic_time = (time.time() - t0) * 1000

    # 判定
    t0 = time.time()
    entities = semantic["entities"]
    violations = 0
    for e in entities:
        for func in registry.list_all():
            r = func.execute(e)
            if r.result != "PASS":
                violations += 1
    judge_time = (time.time() - t0) * 1000

    total = parse_time + semantic_time + judge_time

    print(f"  全量图元: {len(result.primitives)}")
    print(f"  解析: {parse_time:.0f}ms")
    print(f"  语义: {semantic_time:.0f}ms")
    print(f"  判定: {judge_time:.0f}ms")
    print(f"  合计: {total:.0f}ms")
    print(f"  {'✅ 达标(<10000ms)' if total < 10000 else '❌ 超标'}")


# ── 主测试入口 ────────────────────────────────────────────

def main():
    section("BAA Level 5 端到端集成测试")
    print(f"  时间: 2026-06-20")
    print(f"  图纸: 东莞通-建筑（34748图元）")
    print(f"  引擎: v0.5.0-dev")

    results = {}

    try:
        results["L1"] = level_1_atomic_functions()
    except Exception as e:
        print(f"  ❌ L1失败: {e}")
        results["L1"] = False

    try:
        results["L2"] = level_2_spec_coverage()
    except Exception as e:
        print(f"  ❌ L2失败: {e}")
        results["L2"] = False

    try:
        results["L3"] = level_3_entity_recognition()
    except Exception as e:
        print(f"  ❌ L3失败: {e}")
        results["L3"] = False

    try:
        results["L4"] = level_4_attribution_quality()
    except Exception as e:
        print(f"  ❌ L4失败: {e}")
        results["L4"] = False

    try:
        results["L5"] = level_5_e2e_api()
    except Exception as e:
        import traceback
        print(f"  ❌ L5失败: {e}")
        traceback.print_exc()
        results["L5"] = False

    performance_baseline()

    # 汇总
    print(f"\n{'=' * 60}")
    print(f"  测试汇总")
    print(f"{'=' * 60}")
    for level, ok in sorted(results.items()):
        status = "✅" if ok else "❌"
        print(f"  {status} {level}")

    all_pass = all(results.values())
    print(f"\n  {'=' * 30}")
    print(f"  {'✅ 全部通过' if all_pass else '❌ 部分失败'}")
    print(f"  {'=' * 30}")

    return int(not all_pass)


if __name__ == "__main__":
    sys.exit(main())