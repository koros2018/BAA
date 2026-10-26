"""T-C7 OCR 解阻塞：扫描件/栅格图文字识别。

设计要点：
- 引擎为 tesseract + chi_sim（Apache-2.0，无 AGPL 约束，可在主进程内调用）
- 预处理：灰度 → Otsu 二值化 → 等效 DPI 不足 200 时升采样
- 输出带位置与置信度的 OcrToken，供后续回填图纸审查管道
- 引擎缺失时所有入口优雅降级（返回空 / available=False），不抛异常

环境变量：
- BAA_TESSERACT_CMD：tesseract 可执行文件路径（缺省自动探测）
- TESSDATA_PREFIX：tessdata 目录（缺省自动探测仓库内 tessdata/）
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MIN_DPI = 200  # 验收基线：≥200DPI


@dataclass
class OcrToken:
    """单个 OCR 识别结果。"""

    text: str
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1（像素）
    confidence: float  # 0~100（tesseract 原生口径）
    line_id: int = 0  # 同一文本行的分组标识（block*10000 + par*100 + line）


def find_tesseract() -> Optional[str]:
    """定位 tesseract 可执行文件，找不到返回 None。"""
    env = os.getenv("BAA_TESSERACT_CMD")
    if env and Path(env).is_file():
        return env
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    candidates = [
        # conda（本机 miniconda）安装路径
        Path(sys.executable).resolve().parent.parent / "Library" / "bin" / "tesseract.exe",
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def find_tessdata() -> Optional[str]:
    """定位含 chi_sim.traineddata 的 tessdata 目录。"""
    env = os.getenv("TESSDATA_PREFIX")
    if env and (Path(env) / "chi_sim.traineddata").is_file():
        return env
    repo_dir = _PROJECT_ROOT / "tessdata"
    if (repo_dir / "chi_sim.traineddata").is_file():
        return str(repo_dir)
    # tesseract 自带 tessdata（通常仅 eng）
    exe = find_tesseract()
    if exe:
        default_dir = Path(exe).resolve().parent.parent / "share" / "tessdata"
        if default_dir.is_dir():
            return str(default_dir)
    return None


def tesseract_available() -> bool:
    """引擎与中文语言包均可用才视为可用。"""
    exe = find_tesseract()
    if not exe:
        return False
    tessdata = find_tessdata()
    return bool(tessdata and (Path(tessdata) / "chi_sim.traineddata").is_file())


def ocr_available_reason() -> str:
    """诊断用：说明不可用的原因。"""
    if not find_tesseract():
        return "tesseract 可执行文件未找到（BAA_TESSERACT_CMD / PATH / conda）"
    if not tesseract_available():
        return "chi_sim.traineddata 未找到（TESSDATA_PREFIX / 仓库 tessdata/）"
    return "ok"


def _to_grayscale_array(img):
    """PIL Image → 灰度 numpy 数组。"""
    import numpy as np

    return np.asarray(img.convert("L"))


def _otsu_threshold(gray) -> int:
    """Otsu 法求二值化阈值（避免引入 cv2 依赖）。"""
    import numpy as np

    hist, _ = np.histogram(gray, bins=256, range=(0, 256))
    total = gray.size
    sum_total = float(np.dot(np.arange(256), hist))
    sum_b = 0.0
    w_b = 0.0
    best_var = -1.0
    best_t = 127
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > best_var:
            best_var = var_between
            best_t = t
    return best_t


def preprocess(img, source_dpi: Optional[float] = None, min_dpi: int = _MIN_DPI):
    """灰度 + Otsu 二值化 + 等效 DPI 不足时升采样。

    source_dpi 为图像原始等效 DPI；缺省按 96 DPI 估算（屏幕截图/普通渲染件）。
    """
    from PIL import Image

    dpi = source_dpi or 96.0
    if dpi < min_dpi:
        factor = min_dpi / dpi
        new_size = (max(1, round(img.width * factor)), max(1, round(img.height * factor)))
        img = img.resize(new_size, Image.LANCZOS)
        logger.debug("[T-C7] 升采样 %sx%s（%.0f→%d DPI）", *new_size, dpi, min_dpi)

    gray = _to_grayscale_array(img)
    threshold = _otsu_threshold(gray)
    import numpy as np

    binary = np.where(gray > threshold, 255, 0).astype(np.uint8)
    return Image.fromarray(binary, mode="L")


def _run_tesseract_data(img, lang: str = "chi_sim", psm: int = 11) -> List[OcrToken]:
    """调用 pytesseract image_to_data 并整理为 OcrToken 列表。

    psm=11（sparse text）：图纸标注为稀疏分布文本，比整页模式更适配。
    lang 默认 chi_sim：模型自带拉丁/数字能力，混挂 eng 反而将汉字误判为拉丁字符。
    """
    import pytesseract
    from pytesseract import Output

    exe = find_tesseract()
    if exe:
        pytesseract.pytesseract.tesseract_cmd = exe
    tessdata = find_tessdata()
    config = f"--psm {psm}"
    # 通过 TESSDATA_PREFIX 传语言包目录（config 内嵌带空格路径会被 tesseract 误解析）
    prev_prefix = os.environ.get("TESSDATA_PREFIX")
    if tessdata:
        os.environ["TESSDATA_PREFIX"] = tessdata
    try:
        data = pytesseract.image_to_data(img, lang=lang, config=config, output_type=Output.DICT)
    finally:
        if tessdata:
            if prev_prefix is None:
                os.environ.pop("TESSDATA_PREFIX", None)
            else:
                os.environ["TESSDATA_PREFIX"] = prev_prefix
    tokens: List[OcrToken] = []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < 0:  # tesseract 对非文本块给 -1
            continue
        x, y, w, h = (
            data["left"][i],
            data["top"][i],
            data["width"][i],
            data["height"][i],
        )
        line_id = (
            int(data["block_num"][i]) * 10000
            + int(data["par_num"][i]) * 100
            + int(data["line_num"][i])
        )
        tokens.append(
            OcrToken(
                text=text,
                bbox=(float(x), float(y), float(x + w), float(y + h)),
                confidence=conf,
                line_id=line_id,
            )
        )
    return tokens


def ocr_image(
    img,
    *,
    lang: str = "chi_sim",
    psm: int = 11,
    source_dpi: Optional[float] = None,
    min_dpi: int = _MIN_DPI,
    do_preprocess: bool = True,
) -> List[OcrToken]:
    """对 PIL Image 做 OCR。引擎不可用时返回空列表。"""
    if not tesseract_available():
        logger.warning("[T-C7] OCR 不可用：%s", ocr_available_reason())
        return []
    if do_preprocess:
        img = preprocess(img, source_dpi=source_dpi, min_dpi=min_dpi)
    return _run_tesseract_data(img, lang=lang, psm=psm)


def ocr_file(
    path: str,
    *,
    lang: str = "chi_sim",
    psm: int = 11,
    source_dpi: Optional[float] = None,
    min_dpi: int = _MIN_DPI,
) -> List[OcrToken]:
    """对图像文件（PNG/JPG/TIFF/BMP）做 OCR。"""
    from PIL import Image

    img = Image.open(path)
    if source_dpi is None:
        dpi_info = img.info.get("dpi")
        if dpi_info and dpi_info[0] > 0:
            source_dpi = float(dpi_info[0])
    return ocr_image(img, lang=lang, psm=psm, source_dpi=source_dpi, min_dpi=min_dpi)


# ── 识别率评估（验收口径）────────────────────────────────


def _normalize(text: str) -> str:
    """归一化：去空白与常用全角冒号差异，便于模糊匹配。"""
    return "".join(text.split()).replace("：", ":")


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def group_lines(tokens: Sequence[OcrToken]) -> List[str]:
    """将 token 按行分组并拼接为行文本（按 x 坐标排序，无空格拼接）。"""
    lines: dict[int, List[OcrToken]] = {}
    for t in tokens:
        lines.setdefault(t.line_id, []).append(t)
    out = []
    for line_id in sorted(lines):
        toks = sorted(lines[line_id], key=lambda t: t.bbox[0])
        out.append("".join(t.text for t in toks))
    return out


def _containment(gt: str, candidate: str) -> float:
    """GT 在候选文本中的最长连续覆盖率（0~1）。"""
    g = _normalize(gt)
    c = _normalize(candidate)
    if not g:
        return 1.0
    if not c:
        return 0.0
    if g in c:
        return 1.0
    m = SequenceMatcher(None, g, c).find_longest_match(0, len(g), 0, len(c))
    return m.size / len(g)


def recognition_rate(
    tokens: Sequence[OcrToken],
    ground_truth: Iterable[str],
    *,
    similarity_threshold: float = 0.6,
) -> dict:
    """对照真值计算识别率。

    匹配口径：GT 归一化后与每个 OCR 行文本比对，
    整行相似度 ≥ 阈值 或 GT 最长连续覆盖率 ≥ 阈值 均计为识别成功
    （覆盖率口径兼容 GT 为一行中片段、OCR 行内空格差异等情形）。
    返回 {total, matched, rate, missed}。
    """
    gt = [g for g in ground_truth if _normalize(g)]
    ocr_lines = group_lines(tokens)
    ocr_texts = [t.text for t in tokens]
    matched = 0
    missed: List[str] = []
    for g in gt:
        hit = False
        for text in ocr_lines + ocr_texts:
            if _similarity(g, text) >= similarity_threshold:
                hit = True
                break
            if _containment(g, text) >= similarity_threshold:
                hit = True
                break
        if hit:
            matched += 1
        else:
            missed.append(g)
    total = len(gt)
    return {
        "total": total,
        "matched": matched,
        "rate": (matched / total) if total else 0.0,
        "missed": missed,
    }
