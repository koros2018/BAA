"""T-C7 OCR 解阻塞 单元测试。

覆盖：
- 引擎/语言包探测（find_tesseract / find_tessdata / tesseract_available）
- 预处理（升采样至 ≥200DPI、灰度、Otsu 二值化）
- 识别率口径（recognition_rate / group_lines / 归一化 / 覆盖率）
- PDF 隔离子进程 probe / render-png（AGPL 边界不破）
- 扫描件全链路：合成栅格 PDF → is_scanned_pdf → OCR → TEXT 实体

OCR 引擎缺失时全链路用例 skip（CI 无 tesseract 不阻塞）。
"""

import os

import pytest

from src.baa_engine.ocr_text import (
    OcrToken,
    find_tesseract,
    find_tessdata,
    group_lines,
    ocr_available_reason,
    preprocess,
    recognition_rate,
    tesseract_available,
    _containment,
    _normalize,
    _otsu_threshold,
)
from src.baa_engine.parsers.pdf_isolation import (
    probe_pdf_isolated,
    render_pdf_page_isolated,
)
from src.baa_engine.scan_ingest import (
    is_scanned_pdf,
    ocr_scanned_pdf,
    tokens_to_text_entities,
)

TESS_MARK = pytest.mark.skipif(
    not tesseract_available(),
    reason=f"tesseract/chi_sim 不可用：{ocr_available_reason()}",
)


def _pymupdf():
    return pytest.importorskip("pymupdf")


# ── 引擎探测 ─────────────────────────────────────────────


def test_find_tesseract_returns_path_or_none():
    exe = find_tesseract()
    if exe is not None:
        assert os.path.isfile(exe)


def test_find_tessdata_consistency():
    tessdata = find_tessdata()
    if tesseract_available():
        assert tessdata is not None
        assert os.path.isfile(os.path.join(tessdata, "chi_sim.traineddata"))
    assert isinstance(ocr_available_reason(), str)


def test_ocr_available_reason_matches_availability():
    if tesseract_available():
        assert ocr_available_reason() == "ok"
    else:
        assert ocr_available_reason() != "ok"


# ── 预处理 ───────────────────────────────────────────────


def test_preprocess_upsamples_low_dpi():
    from PIL import Image

    img = Image.new("RGB", (100, 60), 255)
    out = preprocess(img, source_dpi=96.0, min_dpi=200)
    # 96 → 200 DPI 需约 2.08 倍升采样
    assert out.width >= 200
    assert out.height >= 120
    assert out.mode == "L"


def test_preprocess_keeps_high_dpi_size():
    from PIL import Image

    img = Image.new("L", (300, 200), 255)
    out = preprocess(img, source_dpi=300.0, min_dpi=200)
    assert out.size == (300, 200)


def test_otsu_threshold_separates_bimodal():
    import numpy as np

    # 双峰：一半 20（文字），一半 235（背景）
    gray = np.concatenate(
        [np.full(5000, 20, dtype=np.uint8), np.full(5000, 235, dtype=np.uint8)]
    )
    t = _otsu_threshold(gray)
    assert 20 <= t < 235


def test_preprocess_binarizes_output():
    import numpy as np
    from PIL import Image, ImageDraw

    img = Image.new("L", (200, 100), 255)
    d = ImageDraw.Draw(img)
    d.rectangle([40, 30, 160, 70], fill=0)
    out = preprocess(img, source_dpi=300.0)
    arr = np.asarray(out)
    assert set(np.unique(arr)).issubset({0, 255})


# ── 识别率口径 ───────────────────────────────────────────


def _tok(text, line_id=1, x=0.0):
    return OcrToken(text=text, bbox=(x, 0.0, x + 10.0, 10.0), confidence=90.0, line_id=line_id)


def test_normalize_strips_whitespace_and_fullwidth_colon():
    assert _normalize(" 疏散通道 宽度：1.20m ") == "疏散通道宽度:1.20m"


def test_group_lines_orders_tokens_by_x():
    tokens = [
        OcrToken("宽度", (50, 0, 90, 10), 90, 7),
        OcrToken("疏散", (0, 0, 40, 10), 90, 7),
        OcrToken("另一行", (0, 20, 60, 30), 90, 8),
    ]
    lines = group_lines(tokens)
    assert lines == ["疏散宽度", "另一行"]


def test_containment_full_and_partial():
    assert _containment("疏散通道", "xx疏散通道yy") == 1.0
    # GT 6 字，候选覆盖 4 字 → 最长连续覆盖 4/6
    assert _containment("疏散通道宽度", "疏散通道") == pytest.approx(4 / 6)
    assert _containment("不存在", "完全无关") == 0.0


def test_recognition_rate_all_matched():
    tokens = [_tok("一层平面图", line_id=1), _tok("防火门FM乙1021", line_id=2)]
    r = recognition_rate(tokens, ["一层平面图", "防火门 FM乙1021"])
    assert r["total"] == 2
    assert r["matched"] == 2
    assert r["rate"] == 1.0
    assert r["missed"] == []


def test_recognition_rate_fragmented_tokens_containment():
    # token 碎片化：GT 为一整行，OCR 拆为多个 token，行拼接后应命中
    tokens = [
        OcrToken("疏散通道宽度", (0, 0, 100, 10), 90, 1),
        OcrToken("1.20m", (110, 0, 160, 10), 90, 1),
    ]
    r = recognition_rate(tokens, ["疏散通道宽度 1.20m"])
    assert r["matched"] == 1


def test_recognition_rate_missed_reported():
    tokens = [_tok("完全无关的内容")]
    r = recognition_rate(tokens, ["楼梯间前室面积6.0㎡"])
    assert r["matched"] == 0
    assert r["rate"] == 0.0
    assert r["missed"] == ["楼梯间前室面积6.0㎡"]


def test_recognition_rate_empty_ground_truth():
    r = recognition_rate([_tok("任意")], ["", "   "])
    assert r["total"] == 0
    assert r["rate"] == 0.0  # 无真值时不计识别率


# ── PDF 隔离 probe / render ──────────────────────────────


def _make_vector_pdf(path):
    pymupdf = _pymupdf()
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=300)
    for i in range(20):
        page.draw_line(pymupdf.Point(10, 10 + i * 10), pymupdf.Point(390, 10 + i * 10))
    page.insert_text(pymupdf.Point(50, 280), "vector page")
    doc.save(str(path))
    doc.close()


def _make_scanned_pdf(path):
    """整页一张大图、零矢量 = 典型扫描件形态。"""
    pymupdf = _pymupdf()
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("L", (1240, 877), 255)  # A4 横版 @150DPI 近似
    d = ImageDraw.Draw(img)
    d.rectangle([30, 30, 1210, 847], outline=0, width=2)
    font = None
    for cand in ["C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/msyh.ttc"]:
        if os.path.isfile(cand):
            font = ImageFont.truetype(cand, 48)
            break
    if font:
        d.text((100, 100), "一层平面图", fill=0, font=font)
        d.text((100, 250), "疏散通道宽度1.20m", fill=0, font=font)
        d.text((100, 400), "防火门FM乙1021", fill=0, font=font)
    else:
        d.text((100, 100), "FLOOR PLAN LEVEL 1", fill=0)
        d.text((100, 250), "EXIT CORRIDOR WIDTH 1.20m", fill=0)
    img.save(str(path.with_suffix(".png")), dpi=(150, 150))

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=421)
    page.insert_image(pymupdf.Rect(0, 0, 595, 421), filename=str(path.with_suffix(".png")))
    doc.save(str(path))
    doc.close()


def test_probe_pdf_isolated_vector(tmp_path):
    pdf = tmp_path / "vector.pdf"
    _make_vector_pdf(pdf)
    probe = probe_pdf_isolated(str(pdf))
    assert probe is not None
    assert probe["lines"] >= 20
    assert probe["is_raster"] is False


def test_probe_pdf_isolated_scanned(tmp_path):
    pdf = tmp_path / "scan.pdf"
    _make_scanned_pdf(pdf)
    probe = probe_pdf_isolated(str(pdf))
    assert probe is not None
    assert probe["images"] >= 1
    assert probe["is_raster"] is True


def test_render_pdf_page_isolated(tmp_path):
    pdf = tmp_path / "vector.pdf"
    _make_vector_pdf(pdf)
    out = tmp_path / "page0.png"
    result = render_pdf_page_isolated(str(pdf), str(out), dpi=200)
    assert result is not None
    assert os.path.isfile(out)
    assert result["dpi"] == 200
    assert result["width"] > 0 and result["height"] > 0


def test_probe_missing_pdf_returns_none(tmp_path):
    assert probe_pdf_isolated(str(tmp_path / "nope.pdf")) is None


# ── 扫描件接入 ───────────────────────────────────────────


def test_is_scanned_pdf(tmp_path):
    vec = tmp_path / "v.pdf"
    scan = tmp_path / "s.pdf"
    _make_vector_pdf(vec)
    _make_scanned_pdf(scan)
    assert is_scanned_pdf(str(vec)) is False
    assert is_scanned_pdf(str(scan)) is True


def test_ocr_scanned_pdf_skips_vector(tmp_path):
    vec = tmp_path / "v.pdf"
    _make_vector_pdf(vec)
    assert ocr_scanned_pdf(str(vec)) is None


def test_tokens_to_text_entities():
    tokens = [
        OcrToken("一层平面图", (10.0, 20.0, 110.0, 60.0), 95.0, 3),
        OcrToken("1.20m", (120.0, 20.0, 180.0, 60.0), 88.0, 3),
    ]
    ents = tokens_to_text_entities(tokens)
    assert len(ents) == 2
    assert ents[0]["type"] == "text"
    assert ents[0]["layer"] == "OCR"
    assert ents[0]["bbox"] == [10.0, 20.0, 110.0, 60.0]
    assert ents[0]["properties"]["text"] == "一层平面图"
    assert ents[0]["properties"]["confidence"] == 95.0
    assert ents[0]["properties"]["source"] == "ocr"
    assert ents[1]["id"] == "ocr-1"


# ── 全链路（需 tesseract + chi_sim）──────────────────────


@TESS_MARK
def test_full_chain_scanned_pdf_ocr(tmp_path):
    """合成扫描件全链路：probe 判栅格 → 渲染 300DPI → OCR → 识别率 ≥85%（验收口径）。"""
    pdf = tmp_path / "scan.pdf"
    _make_scanned_pdf(pdf)

    tokens = ocr_scanned_pdf(str(pdf))
    assert tokens is not None
    assert len(tokens) > 0

    # 真值与 _make_scanned_pdf 内绘制文本一致
    font_zh = os.path.isfile("C:/Windows/Fonts/simhei.ttf") or os.path.isfile(
        "C:/Windows/Fonts/msyh.ttc"
    )
    gt = (
        ["一层平面图", "疏散通道宽度1.20m", "防火门FM乙1021"]
        if font_zh
        else ["FLOOR PLAN LEVEL 1", "EXIT CORRIDOR WIDTH 1.20m"]
    )
    r = recognition_rate(tokens, gt)
    assert r["rate"] >= 0.85, f"识别率 {r['rate']:.2%}，missed={r['missed']}"
