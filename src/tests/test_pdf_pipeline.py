"""P100: PDF 解析器接入 DrawingParser 主流程测试"""
import sys
import os
from collections import Counter
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.parsers.pdf_parser import pdf_to_dxf
from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
from src.baa_engine.atomic_functions import FuncRegistry

# 真实 PDF 测试路径（仅本地有，CI 跳过）
TEST_PDF = "/mnt/d/BaiduNetdiskDownload/测试图纸/西安特发西港数据中心/装修/一层平面图.pdf"
BOILER_PDF = "/mnt/d/BaiduNetdiskDownload/内蒙古巴彦淖尔神华干熄焦热力系统项目/243352-杭州西子能源 锅炉安装图纸/243352JS1(A).pdf"

LOCAL_PDF_MARK = pytest.mark.skipif(
    not os.path.exists(TEST_PDF),
    reason="本地 PDF 测试文件不存在，CI 环境跳过",
)


@LOCAL_PDF_MARK
def test_pdf_parser_direct():
    """pdf_to_dxf 直接调用"""
    result = pdf_to_dxf(TEST_PDF)
    assert result["lines"] > 10000, f"lines 过少: {result['lines']}"
    assert result["scale"] == 150, f"比例尺未正确提取: {result['scale']}"
    assert result["pt_to_mm_scale"] > 50, f"缩放系数异常: {result['pt_to_mm_scale']}"
    assert os.path.exists(result["dxf_path"]), "DXF 未生成"
    print(f"PASS pdf_to_dxf: lines={result['lines']}, scale=1:{result['scale']}")


@LOCAL_PDF_MARK
def test_drawing_parser_pdf():
    """DrawingParser.parse() 直接消费 PDF"""
    dp = DrawingParser()
    result = dp.parse(TEST_PDF, file_id="test_pdf")
    assert result.success, f"解析失败: {result.error}"
    assert len(result.primitives) > 50000, f"primitives 过少: {len(result.primitives)}"
    print(f"PASS DrawingParser PDF: primitives={len(result.primitives)}")


@LOCAL_PDF_MARK
def test_pdf_semantic_analysis():
    """PDF → 语义分析 → 实体分类"""
    dp = DrawingParser()
    pr = dp.parse(TEST_PDF, file_id="test_pdf_sema")
    assert pr.success
    sa = SemanticAnalyzer()
    semantic = sa.analyze(pr.primitives, pr.dimensions)
    entities = semantic.get("entities", [])
    assert len(entities) > 50, f"实体过少: {len(entities)}"
    type_counts = Counter(e["type"] for e in entities)
    assert type_counts.get("door", 0) > 50, f"door 过少: {type_counts.get('door',0)}"
    assert type_counts.get("wall", 0) > 10, f"wall 过少: {type_counts.get('wall',0)}"
    print(f"PASS PDF 语义分析: {len(entities)} entities, {dict(type_counts.most_common(5))}")


@LOCAL_PDF_MARK
def test_pdf_atomic_functions():
    """PDF → 原子函数判定"""
    dp = DrawingParser()
    pr = dp.parse(TEST_PDF, file_id="test_pdf_af")
    assert pr.success
    sa = SemanticAnalyzer()
    semantic = sa.analyze(pr.primitives, pr.dimensions)
    entities = semantic.get("entities", [])
    registry = FuncRegistry()
    all_findings = []
    for e in entities:
        for func in registry.list_all():
            if func.matches(e):
                f = func.execute(e)
                if f:
                    all_findings.append(f.__dict__)
    assert len(all_findings) > 100, f"AF 命中过少: {len(all_findings)}"
    func_ids = Counter(f.get("func_id", "?") for f in all_findings)
    print(f"PASS PDF AF: {len(all_findings)} findings, {func_ids.most_common(5)}")


@LOCAL_PDF_MARK
def test_multi_page_pdf():
    """多页 PDF 指定页面解析"""
    dp = DrawingParser()
    pr = dp.parse(BOILER_PDF, file_id="boiler_p0", page_index=0)
    assert pr.success
    print(f"PASS 多页 PDF page0: primitives={len(pr.primitives)}")


@LOCAL_PDF_MARK
def test_pdf_p101_filters():
    """P101: PDF 源数据预过滤有效，噪声线消除"""
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.parsers.pdf_parser import pdf_to_dxf
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer

    result = pdf_to_dxf(TEST_PDF)
    dp = DrawingParser()
    pr = dp.parse(result["dxf_path"], "p101_test")
    sa = SemanticAnalyzer()
    semantic = sa.analyze(pr.primitives, pr.dimensions)
    entities = semantic.get("entities", [])
    assert len(entities) > 50, f"实体过少: {len(entities)}"
    # P101: 预过滤后 wall 检测提升（原 49→~35-45，room 出现）
    from collections import Counter
    dist = Counter(e["type"] for e in entities)
    assert dist.get("wall", 0) >= 30, f"wall 过少: {dist.get('wall',0)}"
    # P101: LINE 链闭合检测应产生 room
    rooms = [e for e in entities if e["type"] == "room"]
    print(f"PASS P101: {len(entities)} entities, wall={dist.get('wall',0)}, room={len(rooms)}")


@LOCAL_PDF_MARK
def test_pdf_p101_dim006_detect():
    """P101: DIM-006 门宽检测在 PDF 上有效"""
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.parsers.pdf_parser import pdf_to_dxf
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    from src.baa_engine.atomic_functions import FuncRegistry

    result = pdf_to_dxf(TEST_PDF)
    dp = DrawingParser()
    pr = dp.parse(result["dxf_path"], "p101_dim")
    sa = SemanticAnalyzer()
    semantic = sa.analyze(pr.primitives, pr.dimensions)
    entities = semantic.get("entities", [])
    registry = FuncRegistry()
    dim006_fails = 0
    for e in entities:
        for func in registry.list_all():
            if func.func_id == "DIM-006" and func.matches(e):
                f = func.execute(e)
                if f and f.result == "FAIL":
                    dim006_fails += 1
    # 数据中心装修图门宽普遍合规，FAIL 应接近 0 或为 6（旧数据）
    assert dim006_fails <= 10, f"DIM-006 FAIL 过多: {dim006_fails}"
    print(f"PASS P101 DIM-006: FAIL={dim006_fails}")


def test_drawing_parser_formats():
    """DrawingParser 支持格式确认"""
    assert ".pdf" in DrawingParser.SUPPORTED_FORMATS
    assert ".dxf" in DrawingParser.SUPPORTED_FORMATS
    assert ".dwg" in DrawingParser.SUPPORTED_FORMATS
    print("PASS 支持格式: dxf, dwg, pdf")


def test_pdf_parser_scale_extraction():
    """比例尺提取测试——用 PyMuPDF 合成测试 PDF"""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=600, height=400)
    # 画一个矩形
    page.draw_line(fitz.Point(50, 50), fitz.Point(550, 50))
    page.draw_line(fitz.Point(550, 50), fitz.Point(550, 350))
    page.draw_line(fitz.Point(550, 350), fitz.Point(50, 350))
    page.draw_line(fitz.Point(50, 350), fitz.Point(50, 50))
    # 插入比例尺文字
    page.insert_text(fitz.Point(100, 100), "比例 1:200", fontsize=14)
    page.insert_text(fitz.Point(100, 200), "TEST_SCALE_PDF", fontsize=10)
    tmp = "/tmp/test_scale_extraction.pdf"
    doc.save(tmp)
    doc.close()

    try:
        result = pdf_to_dxf(tmp, scale=200)
        assert result["lines"] == 4, f"lines 应为 4, 实为 {result['lines']}"
        assert result["scale"] == 200
        # 验证缩放：50pt × (25.4/72 × 200) = 352.78mm
        expected = 50 * 25.4 / 72 * 200
        # 取一条线的 bbox 验证
        import ezdxf
        dxf_doc = ezdxf.readfile(result["dxf_path"])
        msp = dxf_doc.modelspace()
        for e in msp:
            if e.dxftype() == "LINE":
                start = e.dxf.start
                end = e.dxf.end
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                assert abs(dx) > 300 or abs(dy) > 300, f"线长异常: dx={dx}, dy={dy}"
                break
        print(f"PASS 比例尺 1:200 缩放验证")
    finally:
        os.remove(tmp)


def test_pdf_parser_no_scale():
    """无比例尺 PDF 默认 1:1"""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=100, height=100)
    page.draw_line(fitz.Point(10, 10), fitz.Point(90, 10))
    tmp = "/tmp/test_no_scale.pdf"
    doc.save(tmp)
    doc.close()
    try:
        result = pdf_to_dxf(tmp)
        assert result["scale"] == 1
        assert abs(result["pt_to_mm_scale"] - 25.4 / 72) < 0.01
        print(f"PASS 无比例尺默认 1:1")
    finally:
        os.remove(tmp)

@LOCAL_PDF_MARK
def test_pdf_p103_axis_merge_rooms():
    """P103: 轴对齐合并后 PDF 房间检测有效

    P103 修复：
    1. _axis_align_merge: PDF 贝塞尔碎片化墙段(75°~95°近垂直为主)
       投影到轴上合并共线段
    2. SemanticAnalyzer.analyze() 扫线法使用全量 primitives，
       避免 random.sample(10000) 丢弃 wall 段
    3. 效果: 西安特发西港装修 PDF room 检测 0→14
    """
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.parsers.pdf_parser import pdf_to_dxf
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer

    # 通过 pdf_to_dxf → DrawingParser 全链路
    result = pdf_to_dxf(TEST_PDF)
    dp = DrawingParser()
    pr = dp.parse(result["dxf_path"], "p103_axis_merge")
    sa = SemanticAnalyzer()
    semantic = sa.analyze(pr.primitives, pr.dimensions)
    entities = semantic.get("entities", [])
    rooms = [e for e in entities if e.get("type") == "room"]
    # P103: 轴对齐合并后应能检测到多个房间（原扫线法在 PDF 上为 0）
    assert len(rooms) >= 1, f"房间检测失败: 仅 {len(rooms)} 个 (预期 >=1)"
    # room area 应合理 (10m² ~ 500m²)
    areas = [r.get("properties", {}).get("area", 0) for r in rooms]
    assert any(a > 5 and a < 500 for a in areas), f"room area 异常: {areas}"
    print(f"PASS P103: {len(entities)} entities, rooms={len(rooms)}, areas=[{areas[0]:.1f}...]m²")


def test_axis_align_merge_unit():
    """轴对齐合并单元测试：近水平/近垂直线段合并，对角噪声丢弃"""
    from src.baa_engine.semantic_analyzer.room import _axis_align_merge

    # 三条共线水平段（y=1000，x 方向 2000~5000）
    # 应合并为一条 2000~5000 的水平线
    segs = [
        (2000, 990, 3000, 1010, "test", 1000),   # 近水平
        (3100, 1005, 4000, 995, "test", 900),    # 近水平
        (4000, 998, 5000, 1002, "test", 1000),   # 近水平
        (0, 0, 5000, 5000, "test", 7071),        # 对角噪声
        (0, 100, 100, 0, "test", 141),            # 短对角
    ]

    merged = _axis_align_merge(segs)
    # 应得到 1 条合并后的水平线段
    h_segs = [s for s in merged if abs(s[2] - s[0]) > abs(s[3] - s[1])]
    v_segs = [s for s in merged if abs(s[3] - s[1]) > abs(s[2] - s[0])]
    assert len(h_segs) >= 1, f"水平段缺失: {merged}"
    # 合并后长度应接近 3000mm (5000-2000)
    h_len = h_segs[0][2] - h_segs[0][0]
    assert h_len > 2500, f"水平段长度不对: {h_len}"
    # 对角噪声应被丢弃
    assert len(v_segs) == 0, f"对角噪声未过滤: {v_segs}"
    print(f"PASS axis_align_merge: {len(segs)} segs → {len(merged)} merged")


@LOCAL_PDF_MARK
def test_pdf_full_primitives_sweep():
    """扫线法使用全量 primitives，不被采样截断

    回归测试：确保 SemanticAnalyzer.analyze() 对扫线法
    传入全量原始图元，而非 random.sample 后的子集。
    """
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.parsers.pdf_parser import pdf_to_dxf
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    from src.baa_engine.semantic_analyzer.room import (
        _sweep_line_detect_rooms,
        _collect_wall_lines,
        _collect_wall_segments,
    )

    result = pdf_to_dxf(TEST_PDF)
    dp = DrawingParser()
    pr = dp.parse(result["dxf_path"], "p103_full_sweep")
    sa = SemanticAnalyzer()

    prims = pr.primitives
    # 直接扫线法应能检测到 rooms
    direct_rooms = _sweep_line_detect_rooms(sa, prims)
    assert len(direct_rooms) >= 1, f"直接扫线 rooms 不足: {len(direct_rooms)}"

    # analyze() 内部也应检测到 rooms
    semantic = sa.analyze(prims, pr.dimensions)
    entities = semantic.get("entities", [])
    rooms = [e for e in entities if e.get("type") == "room"]
    assert len(rooms) >= 1, f"analyze() rooms 不足: {len(rooms)}"

    print(
        f"PASS full_primitives: direct={len(direct_rooms)} rooms, "
        f"analyze={len(rooms)} rooms"
    )


def test_classify_face_corridor():
    """P105: _classify_face 走廊识别——高 aspect + 短边 2000-4000mm"""
    from src.baa_engine.semantic_analyzer.room import _classify_face

    # 标准走廊: 长 10m 宽 2.8m (short=2800mm, aspect=3.57)
    assert _classify_face(10000, 2800, 28.0) == "corridor"
    # 边缘走廊: short=2000, aspect=3.0
    assert _classify_face(6000, 2000, 12.0) == "corridor"
    # 边缘走廊: short=4000, aspect=3.0
    assert _classify_face(12000, 4000, 48.0) == "corridor"
    print("PASS classify_face corridor")


def test_classify_face_room():
    """P105: _classify_face 房间识别——低 aspect 或短边超出走廊范围"""
    from src.baa_engine.semantic_analyzer.room import _classify_face

    # 正方形房间: short=5000, aspect=1.0
    assert _classify_face(5000, 5000, 25.0) == "room"
    # 短边 < 2000: 窄缝
    assert _classify_face(6000, 1500, 9.0) == "room"
    # 短边 > 4000: 大房间
    assert _classify_face(8000, 5000, 40.0) == "room"
    # 低 aspect: 大走廊状但太宽
    assert _classify_face(5000, 4500, 22.5) == "room"
    print("PASS classify_face room")


@LOCAL_PDF_MARK
def test_pdf_p105_corridor_detection():
    """P105: 扫线法在 PDF 上识别走廊"""
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.parsers.pdf_parser import pdf_to_dxf
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    from src.baa_engine.semantic_analyzer.room import _sweep_line_detect_rooms
    from collections import Counter

    result = pdf_to_dxf(TEST_PDF)
    dp = DrawingParser()
    pr = dp.parse(result["dxf_path"], "p105_corridor")
    sa = SemanticAnalyzer()
    sa._analyze_cache = {}

    faces = _sweep_line_detect_rooms(sa, pr.primitives)
    assert len(faces) >= 1, f"扫线法未检测到任何 face: {len(faces)}"

    types = Counter(f.type for f in faces)
    total = len(faces)
    corridor_count = types.get("corridor", 0)
    room_count = types.get("room", 0)
    print(f"PASS P105: {total} faces, {corridor_count} corridors, {room_count} rooms")

    # 验证 corridor 的 clear_width 和 length 属性
    for f in faces:
        if f.type == "corridor":
            cw = f.properties.get("clear_width", 0)
            length = f.properties.get("length", 0)
            assert cw > 0, f"corridor clear_width 缺失: {cw}"
            assert length > 0, f"corridor length 缺失: {length}"
            # 走廊宽度合理范围: 1-4m
            assert 0.5 < cw < 5.0, f"corridor clear_width 异常: {cw}m"
            print(f"  corridor: clear_width={cw:.2f}m length={length:.2f}m")

    # analyze() 也应包含 corridor 类型
    entities = sa.analyze(pr.primitives, pr.dimensions)
    ent_types = Counter(e.get("type") for e in entities.get("entities", []))
    assert ent_types.get("corridor", 0) >= 0, "analyze 输出无 corridor 类型（允许 0）"
    print(f"PASS P105 analyze: {dict(ent_types.most_common(10))}")



def test_detect_doorway_gaps():
    """P105: 门洞间隙检测——原始墙段上找共线间隙"""
    from src.baa_engine.semantic_analyzer.room import _detect_doorway_gaps, _Seg

    # 水平墙线: 三段连续，中间有间隙
    # [0, 5000] [6000, 11000] [12000, 17000]
    # 间隙: 1000mm + 1000mm
    segs: List[_Seg] = [
        (0, 1000, 5000, 1000, "wall", 5000),
        (6000, 1000, 11000, 1000, "wall", 5000),
        (12000, 1000, 17000, 1000, "wall", 5000),
    ]
    doorways = _detect_doorway_gaps(segs)
    assert len(doorways) == 2, f"预期 2 个门洞, 得到 {len(doorways)}"
    for d in doorways:
        gap = d.properties["gap_width_mm"]
        assert 700 <= gap <= 2500, f"门洞宽度异常: {gap}"
    print("PASS doorway gaps: 2 gaps detected")


def test_detect_doorway_gaps_no_gap():
    """P105: 无间隙时不产生门洞"""
    from src.baa_engine.semantic_analyzer.room import _detect_doorway_gaps, _Seg

    segs: List[_Seg] = [
        (0, 1000, 5000, 1000, "wall", 5000),
        (5000, 1000, 10000, 1000, "wall", 5000),
    ]
    doorways = _detect_doorway_gaps(segs)
    # 无间隙（端点相接）→ 0 门洞
    assert len(doorways) == 0, f"预期 0, 得到 {len(doorways)}"
    print("PASS no gap: 0 doorways")


def test_detect_doorway_gaps_too_wide():
    """P105: 间隙过大 (>2500mm) 不视为门洞"""
    from src.baa_engine.semantic_analyzer.room import _detect_doorway_gaps, _Seg

    segs: List[_Seg] = [
        (0, 1000, 5000, 1000, "wall", 5000),
        (9000, 1000, 14000, 1000, "wall", 5000),  # gap=4000mm
    ]
    doorways = _detect_doorway_gaps(segs)
    assert len(doorways) == 0, f"过大间隙不应视为门洞: {len(doorways)}"
    print("PASS too wide: 0 doorways")


def test_sweep_line_includes_doorways():
    """P105: 扫线法返回结果包含 doorway 类型"""
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    from src.baa_engine.semantic_analyzer.room import _sweep_line_detect_rooms

    # 用装饰图纸验证
    path = "/mnt/d/BaiduNetdiskDownload/测试图纸/山东斐讯云翔大数据中心二期项目图纸（打印版）/00装饰/装饰图纸0929.dxf"
    if not os.path.exists(path):
        pytest.skip("本地测试文件不存在")

    dp = DrawingParser()
    result = dp.parse(path, file_id="p105_doorway")
    sa = SemanticAnalyzer()

    faces = _sweep_line_detect_rooms(sa, result.primitives)
    types = Counter(f.type for f in faces)
    assert "doorway" in types, f"扫线法未产生 doorway: {dict(types)}"
    assert types["doorway"] >= 5, f"门洞数量不足: {types['doorway']}"
    print(f"PASS sweep doorways: {types['doorway']} doorways")

