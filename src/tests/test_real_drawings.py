"""
BAA 真实图纸测试基线

验证真实 DWG/DXF 图纸的解析质量和规范判定结果。
每次修改 semantic_analyzer / drawing_parser / atomic_functions 后，
运行此文件确保真实图纸精度不退化。

基线记录：
  2026-07-04 v1.29.0 初始基线建立
  - 新增消防设施实体识别（INSERT 映射 + 图层映射 + TEXT 辅助）
  2026-07-29 v2.5.25 P79/P80 基线更新
  - LAYER_RULES +99% 覆盖，entity 分布微漂移
  2026-08-12 v2.5.33 P101 基线重建
  - data/drawings/real/ 下 7 个 _t3.dxf 文件为天正 T3 空壳 (14KB, 0 entities)
  - 改用 data/files/ 下真实解析后的 DXF（含实际实体数据）+ 东莞通建筑图
  - 基线覆盖 6 张图纸，含 343 rooms 最大图 + 东莞通 148 rooms
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
FILES_DIR = DATA_DIR / "files"  # assignment


def get_real_dxf_paths():  # function: def get_real_dxf_paths():
    """返回所有可用的真实 DXF 路径"""
    paths = []  # assignment
    # P101: 优先从 data/files/ 取有效 DXF
    if FILES_DIR.exists():  # condition: FILES_DIR exists
        for f in sorted(FILES_DIR.glob("*.dxf")):  # loop: iterate
            paths.append(f)  # append to list
    # 东莞通建筑图
    if REAL_DIR.exists():  # condition: REAL_DIR exists
        for f in sorted(REAL_DIR.glob("*.dxf")):  # loop: iterate
            if f not in paths:  # check: membership test
                paths.append(f)  # append to list
    return paths  # return


def _find_dxf(dxf_name):  # function: def _find_dxf(dxf_name):
    """在多个目录中查找 DXF 文件"""
    candidates = []  # assignment
    # 优先从 data/files/ 下查找（真实解析后的 DXF，含实际数据）
    if FILES_DIR.exists():  # condition: FILES_DIR exists
        for f in sorted(FILES_DIR.glob(dxf_name)):  # loop: iterate
            candidates.append(f)  # append to list
    # 递归搜索
    for f in sorted(DATA_DIR.rglob(dxf_name)):  # loop: iterate
        if f not in candidates:  # check: membership test
            candidates.append(f)  # append to list
    candidates = [c for c in candidates if c.exists()]  # function call
    return candidates  # return


# ── 实体类型分布基线 ──
# 格式: {文件名: {实体类型: 数量}}
# 允许 ±30% 浮动（真实图纸解析有自然漂移，parser/语义规则升级后需更新基线）
# 基线日期: 2026-08-12 v2.5.33 (P101 扫线法房间检测)
ENTITY_BASELINE = {  # assignment
    # ── 东莞通建筑图（唯一在 drawings/real/ 中有真实数据的图纸） ──
    "东莞通-建筑-外部参照（不打印）.dxf": {  # code
        "wall": 1482,
        "door": 2644,
        "window": 265,
        "column": 172,
        "room": 148,
        "text": 638,
        "other": 4439,
        "antechamber": 15,
        "fire_elevator": 14,
        "stair": 4,
    },  # code
    # ── 建筑/结构图纸 (data/files/) ──
    "baa-file-00582518a28e.dxf": {  # code
        "room": 343,
        "dimension": 543,
        "text": 320,
        "door": 231,
        "wall": 108,
        "column": 104,
        "window": 27,
        "fire_extinguisher": 14,
        "fire_hydrant": 8,
        "fire_alarm": 4,
        "sprinkler": 2,
    },  # code
    "baa-file-00b3795cf6c2.dxf": {  # code
        "other": 1141,
        "text": 363,
        "door": 321,
        "wall": 180,
        "dimension": 124,
        "window": 107,
        "room": 106,
        "column": 57,
        "stair": 3,
    },  # code
    "baa-file-016c23eb4018.dxf": {  # code
        "dimension": 369,
        "text": 328,
        "wall": 278,
        "stair": 100,
        "column": 88,
        "facade": 86,
        "window": 80,
        "other": 49,
        "equipment": 23,
        "room": 22,
        "floor": 21,
    },  # code
    "baa-file-007a2fa192ad.dxf": {  # code
        "wall": 158,
        "text": 148,
        "slab": 125,
        "footing": 81,
        "room": 28,
        "door": 15,
        "column": 7,
        "water_reservoir": 3,
    },  # code
    "baa-file-019ec606295e.dxf": {  # code
        "foundation": 145,
        "text": 105,
        "room": 72,
        "footing": 49,
        "wall": 40,
        "column": 13,
        "door": 4,
    },  # code
}  # code

# ── EXIST 函数预期结果 ──
EXIST_EXPECTED = {  # assignment
    "baa-file-00582518a28e.dxf": {  # code
        "EXIST-005": "PASS",  # fire_extinguisher=14 / fire_hydrant=8
        "EXIST-006": "PASS",  # fire_alarm=4
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
        "baa-file-00582518a28e.dxf",  # code
        "baa-file-00b3795cf6c2.dxf",  # code
        "baa-file-016c23eb4018.dxf",  # code
        "baa-file-007a2fa192ad.dxf",  # code
        "baa-file-019ec606295e.dxf",  # code
        "东莞通-建筑-外部参照（不打印）.dxf",  # code
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
            # 允许 ±30% 浮动（真实图纸解析有自然漂移，parser 升级后基线更新）
            tolerance = max(int(expected_count * 0.3), 1)  # get maximum
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


@pytest.mark.real_drawing  # code
def test_all_files_dir_parseable(
    parser,
):  # function: def test_all_files_dir_parseable(parser):
    """data/files/ 下随机抽 20 个 DXF 至少能成功解析"""
    if not FILES_DIR.exists():  # condition: FILES_DIR exists
        pytest.skip("data/files/ 不存在")  # function call

    paths = sorted(FILES_DIR.glob("*.dxf"))  # assignment
    assert len(paths) >= 10, f"data/files/ 至少需要 10 个 DXF, 找到 {len(paths)}"  # get length

    # data/files/ 下有很多 0B/mock 垃圾文件，过滤掉 < 50KB 的
    min_size = 50 * 1024  # 50KB
    paths_above_min = [p for p in paths if p.stat().st_size >= min_size]  # assignment
    assert (
        len(paths_above_min) >= 10
    ), f"data/files/ 中 >=50KB 的 DXF 至少需要 10 个, 找到 {len(paths_above_min)}"  # get length

    # 取前 20 个按大小排序的有效 DXF
    sample = sorted(paths_above_min, key=lambda f: f.stat().st_size)[:20]  # 按大小排序取最小的

    failed = []  # assignment
    for p in sample:  # loop: iterate
        try:
            with open(p, "rb") as f:  # context manager
                header = f.read(10)  # 读取文件头
            if not header.startswith(b"  0"):  # 不是 DXF 文件，跳过
                continue  # continue
        except Exception:
            continue
        result = parser.parse(str(p), f"test_{p.stem}")  # function call
        if not result.success or len(result.primitives) == 0:  # check: negated condition
            failed.append((p.name, result.error or "0 primitives"))  # append to list

    assert not failed, f"以下有效 DXF 解析失败:\n" + "\n".join(
        f"  {n}: {e}" for n, e in failed
    )  # function call
    assert len(sample) - len(failed) >= 10, f"有效 DXF 不足: 抽 {len(sample)}, 失败 {len(failed)}"


@pytest.mark.real_drawing  # code
def test_fire_equipment_detection(
    parser, analyzer, registry
):  # function: def test_fire_equipment_detection(parser, analyzer, registry
    """验证含消防设施的建筑图纸正确识别了关键消防设施实体"""
    fire_dxf = "baa-file-00582518a28e.dxf"  # 含 fire_extinguisher=14, fire_hydrant=8

    candidates = _find_dxf(fire_dxf)  # function call
    if not candidates:  # check: negated condition
        pytest.skip(f"找不到 {fire_dxf}")  # function call

    result = parser.parse(str(candidates[0]), f"test_{fire_dxf}")  # function call
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
        f"{fire_dxf}: 未识别出任何消防设施实体\n"
        f"  types available: {dict(type_counts.most_common(10))}"
    )  # 断言: 至少识别出一种消防设施
    # 消防设施合计 >= 3
    key_count = sum(
        fire_types.get(t, 0) for t in ["fire_hydrant", "sprinkler", "fire_extinguisher"]
    )  # 操作
    assert key_count >= 3, (
        f"{fire_dxf}: 关键消防设施合计仅 {key_count} 个, 至少需要 3 个\n"
        f"  fire_types: {fire_types}"
    )  # 断言: 消防设施数量合理
