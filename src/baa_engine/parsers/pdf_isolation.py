"""T-C4 AGPL 隔离：主进程侧的 PDF→DXF 子进程调用封装。

本模块**不导入 PyMuPDF**（AGPL）。PDF 解析通过
`python -m src.baa_engine.parsers.pdf_service` 独立子进程执行，
进程间仅以 CLI 参数 + stdout JSON 通信。

- 默认启用隔离（BAA_PDF_ISOLATION 缺省 "1"）
- BAA_PDF_ISOLATION=0 时回退进程内直接调用（仅本地开发/测试）
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_TIMEOUT = float(os.getenv("BAA_PDF_WORKER_TIMEOUT", "180"))


def pdf_isolation_enabled() -> bool:
    return os.getenv("BAA_PDF_ISOLATION", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _run_worker(args: list, timeout: Optional[float]) -> Optional[dict]:
    """运行 pdf_service 子进程并解析最后一行 JSON 结果。"""
    cmd = [sys.executable, "-m", "src.baa_engine.parsers.pdf_service", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout or _DEFAULT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("[T-C4] PDF 隔离子进程超时: %s", args[0] if args else "")
        return None

    # 结果在 stdout 最后一行 JSON（前面可能有依赖库的告警输出）
    payload = None
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if payload is None:
        logger.warning(
            "[T-C4] PDF 隔离子进程无 JSON 输出 (rc=%s): %s",
            proc.returncode,
            (proc.stderr or "")[-300:],
        )
        return None
    if not payload.get("ok"):
        logger.warning("[T-C4] PDF 隔离子进程失败: %s", payload.get("error"))
        return None
    return payload["result"]


def pdf_to_dxf_isolated(
    pdf_path: str,
    page_index: int = 0,
    scale: Optional[int] = None,
    timeout: Optional[float] = None,
) -> Optional[dict]:
    """在独立子进程中执行 PDF→DXF，返回与 pdf_to_dxf 相同的结果 dict。

    子进程失败/超时/输出非法时返回 None（调用方按解析失败处理）。
    """
    args = [str(pdf_path), "--page", str(page_index)]
    if scale is not None:
        args += ["--scale", str(scale)]
    return _run_worker(args, timeout)


def probe_pdf_isolated(
    pdf_path: str,
    page_index: int = 0,
    timeout: Optional[float] = None,
) -> Optional[dict]:
    """T-C7：统计页面矢量/栅格构成，判定是否为扫描件。

    返回 {page_count, lines, curves, images, text_chars, is_raster} 或 None。
    """
    return _run_worker([str(pdf_path), "--page", str(page_index), "--probe"], timeout)


def render_pdf_page_isolated(
    pdf_path: str,
    out_png: str,
    page_index: int = 0,
    dpi: int = 300,
    timeout: Optional[float] = None,
) -> Optional[dict]:
    """T-C7：将 PDF 页面栅格化为 PNG（供扫描件 OCR）。

    返回 {png, width, height, dpi} 或 None。
    """
    args = [
        str(pdf_path),
        "--page",
        str(page_index),
        "--render-png",
        str(out_png),
        "--dpi",
        str(dpi),
    ]
    return _run_worker(args, timeout)
