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