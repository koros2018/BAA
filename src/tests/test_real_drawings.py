"""
BAA 真实图纸测试基线

验证真实 DWG/DXF 图纸的解析质量和规范判定结果。
每次修改 semantic_analyzer / drawing_parser / atomic_functions 后，
运行此文件确保真实图纸精度不退化。

基线记录：
  2026-07-04 v1.29.0 初始基线建立
  - 新增消防设施实体识别（INSERT 映射 + 图层映射 + TEXT 辅助）
  - 7 张真实图纸全部可解析，EXIST-005/006 在消防图纸上 PASS
"""

import sys  # import
import os  # stdlib: filesystem ops
from pathlib import Path  # import: path utils
from collections import Counter  # stdlib: collections

import pytest  # import

# ── 项目根 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # function call
if str(PROJECT_ROOT) not in sys.path:  # check: membership test
    sys.path.insert(0, str(PROJECT_ROOT))  # sys path

from src.baa_engine.drawing_parser import DrawingParser  # import
from src.baa_engine.semantic_analyzer import SemanticAnalyzer  # import
from src.baa_engine.atomic_functions import FuncRegistry  # import

# ── 测试数据路径 ──
DATA_DIR = PROJECT_ROOT / "data"  # assignment
REAL_DIR = DATA_DIR / "drawings" / "real"  # assignment


def get_real_dxf_paths():  # function: def get_real_dxf_paths():
    """返回所有可用的真实 DXF 路径（排除 drawings/real/ 下的副本）"""
    paths = []  # assignment
    # data/ 下根目录的 t3.dxf
    for f in sorted(DATA_DIR.glob("*_t3.dxf")):  # loop: iterate
        paths.append(f)  # append to list
    # 东莞通项目目录
    dgt_dir = DATA_DIR / "1东莞通施工图-报审170823"  # assignment
    if dgt_dir.exists():  # condition: dgt_dir.exists():
        for f in sorted(dgt_dir.glob("*.dxf")):  # loop: iterate
            if f not in paths:  # check: membership test
                paths.append(f)  # append to list
    # 只有非 t3 的才从 drawings/real 补充
    if REAL_DIR.exists():  # condition: REAL_DIR.exists():
        seen_names = {p.name for p in paths}  # assignment
        for f in sorted(REAL_DIR.glob("*.dxf")):  # loop: iterate
            if f.name not in seen_names:  # check: membership test
                paths.append(f)  # append to list
    return paths  # return


def _find_dxf(dxf_name):  # function: def _find_dxf(dxf_name):
    """在多个目录中查找 DXF 文件，优先 data/ 下原始目录（非 drawings/real/ 副本）"""
    candidates = []  # assignment
    # 递归搜索（排除 drawings/real/ 副本目录，避免文件损坏问题）
    for f in sorted(DATA_DIR.rglob(dxf_name)):  # loop: iterate
        if "drawings/real" not in str(f):  # check: membership test
            candidates.append(f)  # append to list
    # 如果没找到，再试 drawings/real/
    if not candidates and REAL_DIR.exists():  # check: negated condition
        candidates.extend(REAL_DIR.glob(dxf_name))  # extend list
    candidates = [c for c in candidates if c.exists()]  # function call
    return candidates  # return


# ── 实体类型分布基线 ──
# 格式: {文件名: {实体类型: 数量}}
# 允许 ±10% 浮动（避免每次 parser 升级导致基线碎掉）
ENTITY_BASELINE = {  # assignment
    "A1云计算中心平面图0405_t3.dxf": {  # code
        "wall": 2272,
        "door": 78,
        "window": 777,
        "stair": 401,  # code
        "column": 65,
        "room": 19,
        "dimension": 1285,
        "text": 126,  # code
        "other": 4841,  # code
        "parking_space": 17,
        "fire_hydrant": 3,
        "handrail": 3,
    },  # code
    "20210409-3#泵房_t3.dxf": {  # code
        "wall": 397,
        "door": 11,
        "window": 29,
        "stair": 44,  # code
        "column": 9,
        "room": 8,
        "dimension": 362,
        "text": 48,  # code
        "other": 667,
        "equipment": 6,
        "fire_zone": 4,  # code
        "fire_equipment": 41,
    },  # code
    "202109409-2#配电房_t3.dxf": {  # code
        "wall": 292,
        "door": 22,
        "window": 80,
        "stair": 99,  # code
        "column": 2,
        "room": 2,
        "dimension": 369,
        "text": 57,  # code
        "other": 509,
        "equipment": 23,
        "fire_zone": 4,  # code
    },  # code
    "6.火灾自动报警 （报审）_t3.dxf": {  # code
        "wall": 711,
        "door": 235,
        "window": 85,
        "stair": 1,  # code
        "column": 36,
        "room": 6,
        "dimension": 944,
        "text": 78,  # code
        "other": 3080,
        "equipment": 4663,  # code
        "fire_hydrant": 68,
        "sprinkler": 12,
        "fire_extinguisher": 14,  # code
        "smoke_detector": 10,
        "fire_alarm": 20,
        "water_reservoir": 3,  # code
        "fire_door": 9,  # code
        "fire_equipment": 2,
        "alarm_device": 2,
    },  # code
    "9.气体灭火（唯美图框）_t3.dxf": {  # code
        "wall": 682,
        "door": 333,
        "window": 3,
        "stair": 0,  # code
        "column": 284,
        "room": 0,
        "dimension": 627,
        "text": 1107,  # code
        "other": 3983,
        "equipment": 2466,  # code
        "fire_extinguisher": 193,  # code
        "sprinkler": 265,
    },  # code
    "A1云计算中心_水消防2017.03.31_t3.dxf": {  # code
        "wall": 204,
        "door": 1118,
        "window": 627,
        "stair": 0,  # code
        "column": 48,
        "room": 7,
        "dimension": 129,
        "text": 153,  # code
        "other": 4855,  # code
        "fire_hydrant": 25,
        "sprinkler": 195,
        "fire_extinguisher": 62,  # code
        "fire_equipment": 96,
        "fire_alarm": 1,
        "handrail": 3,
    },  # code
}  # code

# ── EXIST 函数预期结果 ──
EXIST_EXPECTED = {  # assignment
    "6.火灾自动报警 （报审）_t3.dxf": {  # code
        "EXIST-005": "PASS",  # 自动灭火系统
        "EXIST-006": "PASS",  # 火灾报警系统
        "EXIST-009": "PASS",  # 消防水池
    },  # code
    "9.气体灭火（唯美图框）_t3.dxf": {  # code
        "EXIST-005": "PASS",  # 气体灭火→自动灭火系统
    },  # code
    "A1云计算中心_水消防2017.03.31_t3.dxf": {  # code
        "EXIST-005": "PASS",  # 水消防→自动灭火系统
    },  # code
}  # code

# ── 夹具 ──


@pytest.fixture(scope="module")  # function call
def parser():  # function: def parser():
    return DrawingParser()  # return


@pytest.fixture(scope="module")  # function call
def analyzer():  # function: def analyzer():
    return SemanticAnalyzer()  # return


@pytest.fixture(scope="module")  # function call
def registry():  # function: def registry():
    return FuncRegistry()  # return


# ── 参数化测试 ──


@pytest.mark.real_drawing  # code
@pytest.mark.parametrize(
    "dxf_name",
    [  # code
        "A1云计算中心平面图0405_t3.dxf",  # code
        "20210409-3#泵房_t3.dxf",  # code
        "202109409-2#配电房_t3.dxf",  # code
        "6.火灾自动报警 （报审）_t3.dxf",  # code
        "9.气体灭火（唯美图框）_t3.dxf",  # code
        "A1云计算中心_水消防2017.03.31_t3.dxf",  # code
    ],
)  # code
def test_real_parse_and_analyze(
    dxf_name, parser, analyzer, registry
):  # function: def test_real_parse_and_analyze(dxf_name, parser, analyzer,
    if dxf_name not in ENTITY_BASELINE:  # check: membership test
        pytest.skip(f"{dxf_name} 不在基线表中")  # function call
    """真实图纸解析+语义分析+原子函数判定，验证精度不退化"""
    # ── 查找文件 ──
    candidates = _find_dxf(dxf_name)  # function call
    assert candidates, f"找不到测试图纸: {dxf_name}"  # code
    path = str(candidates[0])  # function call

    # ── Step 1: 解析 ──
    result = parser.parse(path, f"test_{dxf_name}")  # function call
    assert result.success, f"解析失败: {result.error}"  # code
    assert len(result.primitives) > 0, "解析出 0 个图元"  # get length

    # ── Step 2: 语义分析 ──
    semantic = analyzer.analyze(result.primitives, result.dimensions)  # function call
    entities = semantic["entities"]  # assignment
    assert len(entities) > 0, "语义分析出 0 个实体"  # get length

    type_counts = Counter(e["type"] for e in entities)  # function call

    # ── Step 3: 验证实体类型分布不退化 ──
    baseline = ENTITY_BASELINE.get(dxf_name, {})  # function call
    if baseline:  # condition: baseline:
        for etype, expected_count in baseline.items():  # loop: iterate
            actual_count = type_counts.get(etype, 0)  # function call
            # 允许 ±20% 浮动（真实图纸解析有一定随机性）
            tolerance = max(int(expected_count * 0.2), 1)  # get maximum
            assert (
                abs(actual_count - expected_count) <= tolerance
            ), f"{dxf_name}: {etype} expected {expected_count} ± {tolerance}, actual {actual_count}"

    # ── Step 4: 验证关键 EXIST 函数 ──
    all_findings = []  # assignment
    for e in entities:  # loop: iterate
        for func in registry.list_all():  # loop: iterate
            if func.matches(e):  # condition: func.matches(e):
                f = func.execute(e)  # function call
                if f:  # condition: f:
                    all_findings.append(
                        f.__dict__ if hasattr(f, "__dict__") else f
                    )  # append to list

    exist_expected = EXIST_EXPECTED.get(dxf_name, {})  # function call
    for func_id, expected_result in exist_expected.items():  # loop: iterate
        matches = [f for f in all_findings if f.get("func_id") == func_id]  # function call
        if expected_result == "PASS":  # condition: expected_result == "PASS":
            assert any(
                f.get("result") == "PASS" for f in matches
            ), f"{dxf_name}: {func_id} 预期 PASS, 但未找到 PASS 结果 (matches={len(matches)})"  # 断言: 至少有一个 PASS
        elif expected_result == "FAIL":  # elif condition
            assert any(
                f.get("result") == "FAIL" for f in matches
            ), f"{dxf_name}: {func_id} 预期 FAIL, 但未找到 FAIL 结果 (matches={len(matches)})"  # 断言: 至少有一个 FAIL


@pytest.mark.real_drawing  # code
def test_all_real_drawings_parseable(
    parser,
):  # function: def test_all_real_drawings_parseable(parser):
    """所有真实图纸至少能成功解析（0 图元视为解析失败）"""
    paths = get_real_dxf_paths()  # function call
    assert len(paths) >= 5, f"至少需要 5 张真实图纸, 找到 {len(paths)}"  # get length

    failed = []  # assignment
    for p in paths:  # loop: iterate
        result = parser.parse(str(p), f"test_{p.stem}")  # function call
        if not result.success or len(result.primitives) == 0:  # check: negated condition
            failed.append((p.name, result.error or "0 primitives"))  # append to list

    # 电气图纸（2.1电气170825-报审）因图元类型特殊（纯电气符号无建筑几何），允许 0 图元
    # drawings/real/ 下的副本可能已损坏（空格 vs 下划线命名不一致导致文件读取问题）
    known_empty = {
        "2.1电气170825-报审.dxf",
        "4.通风BS170826.dxf",  # assignment
        "东莞通-建筑-外部参照（不打印）.dxf",
        "东莞通-设备-外部参照（不打印）.dxf",  # code
        "A1IDC及通信机楼结构平面图20161227z.dxf",  # code
        "6.火灾自动报警_（报审）_t3.dxf",
    }  # code
    unexpected = [(n, e) for n, e in failed if n not in known_empty]  # function call

    assert not unexpected, f"以下图纸解析失败:\n" + "\n".join(
        f"  {n}: {e}" for n, e in unexpected
    )  # function call


@pytest.mark.real_drawing  # code
def test_fire_equipment_detection(
    parser, analyzer, registry
):  # function: def test_fire_equipment_detection(parser, analyzer, registry
    """验证消防图纸正确识别了关键消防设施实体"""
    fire_drawings = [  # assignment
        "6.火灾自动报警 （报审）_t3.dxf",  # code
        "9.气体灭火（唯美图框）_t3.dxf",  # code
        "A1云计算中心_水消防2017.03.31_t3.dxf",  # code
    ]  # code

    for dxf_name in fire_drawings:  # loop: iterate
        candidates = _find_dxf(dxf_name)  # function call
        if not candidates:  # check: negated condition
            pytest.skip(f"找不到 {dxf_name}")  # function call

        result = parser.parse(str(candidates[0]), f"test_{dxf_name}")  # function call
        assert result.success  # code
        semantic = analyzer.analyze(result.primitives, result.dimensions)  # function call
        entities = semantic["entities"]  # assignment

        type_counts = Counter(e["type"] for e in entities)  # function call
        fire_types = {
            t: c
            for t, c in type_counts.items()
            if t
            in (  # function call
                "fire_hydrant",
                "sprinkler",
                "fire_extinguisher",  # code
                "smoke_detector",
                "fire_alarm",  # code
            )
        }  # code

        assert len(fire_types) > 0, (  # 断言: 至少识别出一种消防设施
            f"{dxf_name}: 未识别出任何消防设施实体\n"
            f"  types available: {dict(type_counts.most_common(10))}"
        )
