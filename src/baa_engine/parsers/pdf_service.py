"""T-C4 AGPL 隔离：PDF→DXF 独立进程 Worker（CLI）

用法：
    python -m src.baa_engine.parsers.pdf_service <pdf_path> [--page N] [--scale N]

- 唯一导入 PyMuPDF（AGPL-3.0 / Artifex 商业双许可）的进程入口。
- 主服务进程（FastAPI/审查管线）**不导入 PyMuPDF**，通过本 CLI 子进程调用，
  两进程间仅以命令行参数 + stdout JSON 通信（进程边界 = 许可边界）。
- 结果以最后一行 JSON 输出：{"ok": true, "result": {...}} 或 {"ok": false, "error": "..."}
"""

import json
import sys


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="BAA PDF→DXF isolated worker (AGPL)")
    parser.add_argument("pdf_path")
    parser.add_argument("--page", type=int, default=0)
    parser.add_argument("--scale", type=int, default=None)
    args = parser.parse_args(argv)

    try:
        # PyMuPDF 仅在本独立进程内加载（AGPL 组件边界）
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
