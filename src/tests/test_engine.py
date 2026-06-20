"""
BAA 核心引擎测试
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.baa_engine.atomic_functions import FuncRegistry, AtomicFunction, FuncCategory
from src.baa_engine.spec_repository import SpecRepository
from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.attribution_analyzer import AttributionAnalyzer


def test_func_registry_initial():
    """测试原子函数注册表初始化"""
    registry = FuncRegistry()
    assert registry.count == 10, f"应有10个初始函数，实际{registry.count}"
    assert registry.capacity == 30, f"框架应为30个位置"


def test_func_registry_get():
    """测试获取原子函数"""
    registry = FuncRegistry()
    func = registry.get("DIM-001")
    assert func is not None
    assert func.func_id == "DIM-001"
    assert func.name == "疏散楼梯净宽判定"
    assert func.threshold == 1.2


def test_func_execute_fail():
    """测试判定失败"""
    registry = FuncRegistry()
    func = registry.get("DIM-001")
    entity = {
        "id": "ST_001",
        "type": "staircase",
        "properties": {"clear_width": 1.05},
    }
    result = func.execute(entity)
    assert result.result == "FAIL"
    assert result.delta < 0


def test_func_execute_pass():
    """测试判定通过"""
    registry = FuncRegistry()
    func = registry.get("DIM-001")
    entity = {
        "id": "ST_002",
        "type": "staircase",
        "properties": {"clear_width": 1.30},
    }
    result = func.execute(entity)
    assert result.result == "PASS"
    assert result.delta > 0


def test_spec_repository():
    """测试规范库"""
    repo = SpecRepository()
    assert repo.count == 10

    clause = repo.get("GB50016-5.5.18")
    assert clause is not None
    assert clause.level == "L1"
    assert clause.func_id == "DIM-001"


def test_spec_repository_by_func():
    """测试通过函数ID查规范"""
    repo = SpecRepository()
    clauses = repo.get_by_func("DIM-001")
    assert len(clauses) >= 1


def test_spec_repository_to_json():
    """测试规范序列化"""
    repo = SpecRepository()
    json_str = repo.to_json()
    assert len(json_str) > 0
    assert "GB50016-5.5.18" in json_str


def test_attribution_analyzer():
    """测试归因分析"""
    from src.baa_engine.atomic_functions import FuncRegistry, Severity
    from dataclasses import dataclass

    analyzer = AttributionAnalyzer()
    registry = FuncRegistry()

    # 模拟函数判定结果
    class MockFuncResult:
        def __init__(self):
            self.func_id = "DIM-001"
            self.operator = ">="
            self.threshold = 1.2
            self.actual = 1.05
            self.result = "FAIL"
            self.delta = -0.15
            self.severity = Severity.MAJOR
            self.entity_id = "ST_001"
            self.entity_type = "staircase"
            self.params = {"extracted_key": "clear_width", "unit": "m"}

    func_result = MockFuncResult()
    clause = {"standard": "GB 50016-2014", "clause_id": "GB50016-5.5.18",
              "title": "疏散楼梯净宽", "text": "净宽度不应小于1.2m",
              "category": "fire_safety"}
    entity = {"id": "ST_001", "type": "staircase", "confidence": 0.94}
    related = [{"id": "DR_007", "type": "door"}]

    finding = analyzer.build_finding(func_result, clause, entity, related)

    assert finding.finding_id.startswith("BAA-")
    assert finding.judgement["result"] == "FAIL"
    assert len(finding.attention_map["focus_areas"]) >= 1
    assert len(finding.explanation) > 0
    assert len(finding.suggestion) > 0


def test_drawing_parser_init():
    """测试图纸解析引擎初始化"""
    parser = DrawingParser()
    assert parser is not None


if __name__ == "__main__":
    test_func_registry_initial()
    test_func_registry_get()
    test_func_execute_fail()
    test_func_execute_pass()
    test_spec_repository()
    test_spec_repository_by_func()
    test_spec_repository_to_json()
    test_attribution_analyzer()
    test_drawing_parser_init()
    print("✅ 全部单元测试通过")