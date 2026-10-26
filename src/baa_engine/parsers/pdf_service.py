"""T-C4 AGPL 隔离：PDF→DXF 独立进程 Worker（CLI）

用法：
    python -m src.baa_engine.parsers.pdf_service <pdf_path> [--page N] [--scale N]
    python -m src.baa_engine.parsers.pdf_service <pdf_path> --probe
    python -m src.baa_engine.parsers.pdf_service <pdf_path> --render-png OUT [--page N] [--dpi N]

- 唯一导入 PyMuPDF（AGPL-3.0 / Artifex 商业双许可）的进程入口。
- 主服务进程（FastAPI/审查管线）**不导入 PyMuPDF**，通过本 CLI 子进程调用，
  两进程间仅以命令行参数 + stdout JSON 通信（进程边界 = 许可边界）。
- --probe：返回页面矢量/栅格构成统计（供主进程判定是否为扫描件，T-C7）
- --render-png：将页面按指定 DPI 栅格化为 PNG（供扫描件 OCR，T-C7）
- 结果以最后一行 JSON 输出：{"ok": true, "result": {...}} 或 {"ok": false, "error": "..."}
"""

import json
import sys


def _probe(pdf_path: str, page_index: int) -> dict:
    """统计页面构成：矢量线/曲线数、栅格图像数、可提取文本字符数。"""
    import pymupdf

    doc = pymupdf.open(pdf_path)
    try:
        page = doc[page_index]
        lines = 0
        curves = 0
        for item in page.get_drawings():
            for seg in item.get("items", []):
                if seg[0] == "l":
                    lines += 1
                elif seg[0] == "c":
                    curves += 1
        images = len(page.get_images(full=True))
        text_chars = len(page.get_text().strip())
        return {
            "page_count": doc.page_count,
            "lines": lines,
            "curves": curves,
            "images": images,
            "text_chars": text_chars,
            "is_raster": (lines + curves) < 10 and images > 0,
        }
    finally:
        doc.close()


def _render_png(pdf_path: str, out_path: str, page_index: int, dpi: int) -> dict:
    """将 PDF 页面按指定 DPI 栅格化为 PNG。"""
    import pymupdf

    doc = pymupdf.open(pdf_path)
    try:
        page = doc[page_index]
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        pix.save(out_path)
        return {"png": out_path, "width": pix.width, "height": pix.height, "dpi": dpi}
    finally:
        doc.close()


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="BAA PDF isolated worker (AGPL)")
    parser.add_argument("pdf_path")
    parser.add_argument("--page", type=int, default=0)
    parser.add_argument("--scale", type=int, default=None)
    parser.add_argument("--probe", action="store_true", help="统计页面构成（扫描件判定）")
    parser.add_argument("--render-png", default=None, metavar="OUT", help="栅格化页面为 PNG")
    parser.add_argument("--dpi", type=int, default=300, help="render-png 分辨率")
    args = parser.parse_args(argv)

    try:
        # PyMuPDF 仅在本独立进程内加载（AGPL 组件边界）
        if args.probe:
            print(json.dumps({"ok": True, "result": _probe(args.pdf_path, args.page)}))
            return 0
        if args.render_png:
            result = _render_png(args.pdf_path, args.render_png, args.page, args.dpi)
            print(json.dumps({"ok": True, "result": result}))
            return 0

        from src.baa_engine.parsers.pdf_parser import pdf_to_dxf

        result = pdf_to_dxf(args.pdf_path, page_index=args.page, scale=args.scale)
        if result is None:
            print(json.dumps({"ok": False, "error": "PDF 解析失败：无法提取矢量数据"}))
            return 2
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        return 0
    except Exception as e:  # 子进程错误以 JSON 回报，主进程据此判失败
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
