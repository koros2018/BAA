"""Linux CI 全量回归验证脚本 —— 2026-10-15 Windows 兼容性修复的跨平台确认

对应清单: docs/cross-platform-checklist-20261015.md 遗留行动项 1
  "Linux CI 补跑全量回归，确认 F1 候选列表前 5 项与 F2 语义无漂移"

阶段:
  0. 环境自检（python/依赖版本）
  1. F1 静态漂移检查: 字体候选列表前 5 项必须仍为 Linux 路径（顺序敏感）
  2. F1 运行时行为: 存在 CJK 字体或 BAA_PDF_FONT 时跑 PDF 测试组（否则 SKIP 并提示）
  3. F2 语义检查: reverse_engine 必须用 shutil.which（禁止 subprocess ["which"]），
     且 LibreOffice 缺席时 _export_via_libreoffice 优雅降级返回 False
  4. 全量回归: pytest -m "not slow and not real_drawing"（任一失败即 FAIL）
  5. real_drawing 基线: pytest -m real_drawing（data/ 缺失时 SKIP）

用法:
  python scripts/linux_ci_regression.py               # 全阶段
  python scripts/linux_ci_regression.py --probes-only # 仅阶段 0-3（快速漂移自检）

退出码: 0 = 全部必选阶段通过；1 = 存在 FAIL
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── 期望基线（与 2026-10-15 修复后的源码一致，顺序敏感） ──
_EXPECTED_LINUX_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttf",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/tmp/wqy-zenhei.ttf",
]
_EXPECTED_WINDOWS_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
]
_EXPECTED_MACOS_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
]

# Windows 参考基线（2026-10-15 全量回归实测），仅用于漂移提示，不作硬性判定
_REFERENCE_FULL = "2246 passed, 14 skipped"
_REFERENCE_REAL_DRAWING = "8 passed"

RESULTS = []  # (stage, name, status, detail)


def record(stage, name, status, detail=""):
    RESULTS.append((stage, name, status, detail))
    mark = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[status]
    print(f"  {mark} {name}" + (f" —— {detail}" if detail else ""))


def run_pytest(args, timeout=900):
    """运行 pytest 并返回 (returncode, passed_count, tail_output)"""
    cmd = [sys.executable, "-m", "pytest", "--tb=short", "-q"] + args
    try:
        proc = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return -1, 0, "TIMEOUT"
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"(\d+) passed(?:, (\d+) skipped)?", out)
    passed = int(m.group(1)) if m else 0
    tail = "\n".join(out.strip().splitlines()[-25:])
    return proc.returncode, passed, tail


# ── 阶段 1: F1 候选列表静态漂移检查 ──────────────────────────

def _parse_font_candidates():
    """从 components.py 源码解析 ensure_font 内的 candidates 列表"""
    src = (ROOT / "src/baa_engine/report_generator/components.py").read_text(
        encoding="utf-8"
    )
    anchor = src.find('BAA_PDF_FONT')
    if anchor < 0:
        raise RuntimeError("components.py 未找到 BAA_PDF_FONT 锚点")
    m = re.compile(r"candidates\s*=\s*\[(.*?)\]", re.DOTALL).search(src, anchor)
    if not m:
        raise RuntimeError("components.py 未找到 candidates 列表")
    return re.findall(r'"([^"]+)"', m.group(1))


def stage_f1_static():
    print("\n===== 阶段 1: F1 字体候选列表静态漂移检查 =====")
    try:
        got = _parse_font_candidates()
    except RuntimeError as e:
        record("1-F1静态", "解析 candidates 列表", "FAIL", str(e))
        return
    expected = (
        _EXPECTED_LINUX_CANDIDATES
        + _EXPECTED_WINDOWS_CANDIDATES
        + _EXPECTED_MACOS_CANDIDATES
    )
    if got == expected:
        record("1-F1静态", "候选列表顺序与内容", "PASS",
               f"前 5 项为 Linux 路径，共 {len(got)} 项，无漂移")
    else:
        # 定位首个差异便于修复
        idx = next((i for i, (a, b) in enumerate(zip(got, expected)) if a != b),
                   min(len(got), len(expected)))
        record("1-F1静态", "候选列表顺序与内容", "FAIL",
               f"第 {idx + 1} 项漂移: 期望 {expected[idx:idx+1]}，实际 {got[idx:idx+1]}")


# ── 阶段 2: F1 字体运行时行为（环境相关） ────────────────────

def stage_f1_runtime():
    print("\n===== 阶段 2: F1 字体运行时行为（PDF 测试组） =====")
    has_env_font = bool(os.environ.get("BAA_PDF_FONT"))
    known_fonts = (
        _EXPECTED_LINUX_CANDIDATES
        + _EXPECTED_WINDOWS_CANDIDATES
        + _EXPECTED_MACOS_CANDIDATES
    )
    has_system_font = any(os.path.exists(p) for p in known_fonts)
    if not (has_env_font or has_system_font):
        record("2-F1运行时", "PDF 测试组", "SKIP",
               "环境无 CJK 字体且未设 BAA_PDF_FONT（CI 环境限制，非回归）"
               "—— 修复: sudo apt-get install -y fonts-wqy-zenhei")
        return
    rc, passed, tail = run_pytest(
        ["src/tests/test_pdf_report.py", "src/tests/test_p119_correction_notice.py"]
    )
    if rc == 0:
        record("2-F1运行时", "PDF 测试组", "PASS", f"{passed} passed")
    else:
        record("2-F1运行时", "PDF 测试组", "FAIL", tail)


# ── 阶段 3: F2 soffice 探测语义 ─────────────────────────────

def stage_f2():
    print("\n===== 阶段 3: F2 soffice 探测语义 =====")
    src = (ROOT / "src/baa_engine/reverse_engine.py").read_text(encoding="utf-8")

    # 静态: 必须用 shutil.which，且不得出现 subprocess ["which", ...] 形式
    if "shutil.which(" in src:
        record("3-F2静态", "shutil.which 跨平台探测", "PASS")
    else:
        record("3-F2静态", "shutil.which 跨平台探测", "FAIL", "源码中未找到 shutil.which")
    if re.search(r'\[\s*["\']which["\']', src):
        record("3-F2静态", "禁用 subprocess which 命令", "FAIL",
               '发现 ["which", ...] 形式（Windows 会 FileNotFoundError）')
    else:
        record("3-F2静态", "禁用 subprocess which 命令", "PASS")

    # 运行时: soffice 缺席时优雅降级（CI 典型场景）
    soffice_on_path = bool(shutil.which("soffice") or shutil.which("libreoffice"))
    try:
        from src.baa_engine.reverse_engine import ReverseEngine

        with tempfile.TemporaryDirectory() as td:
            engine = ReverseEngine()
            ret = engine._export_via_libreoffice(
                os.path.join(td, "in.dxf"), os.path.join(td, "out.dwg")
            )
        if ret is False:
            record("3-F2运行时", "LibreOffice 缺席 → 优雅降级 False", "PASS",
                   "soffice 不在 PATH" if not soffice_on_path else "soffice 在 PATH（转换失败亦降级）")
        else:
            record("3-F2运行时", "LibreOffice 缺席 → 优雅降级 False", "FAIL",
                   f"期望 False，实际 {ret!r}")
    except Exception as e:  # noqa: BLE001 — 任何异常都说明降级失效
        record("3-F2运行时", "LibreOffice 缺席 → 优雅降级 False", "FAIL",
               f"{type(e).__name__}: {e}")


# ── 阶段 4/5: pytest 回归 ───────────────────────────────────

def stage_full_suite():
    print('\n===== 阶段 4: 全量回归 (not slow and not real_drawing) =====')
    rc, passed, tail = run_pytest(
        ["-m", "not slow and not real_drawing", "src/tests/"], timeout=1800
    )
    if rc == 0:
        record("4-全量", "全量回归", "PASS",
               f"{passed} passed（Windows 参考: {_REFERENCE_FULL}，Linux 计数允许合理漂移）")
    else:
        record("4-全量", "全量回归", "FAIL", tail)


def stage_real_drawing():
    print("\n===== 阶段 5: real_drawing 真实图纸基线 =====")
    files_dir = ROOT / "data" / "files"
    real_dir = ROOT / "data" / "drawings" / "real"
    has_data = (files_dir.exists() and any(files_dir.glob("*.dxf"))) or (
        real_dir.exists() and any(real_dir.glob("*.dxf"))
    )
    if not has_data:
        record("5-基线", "real_drawing 基线", "SKIP",
               "data/ 下无 DXF 图纸（CI 需配置图纸数据源）")
        return
    rc, passed, tail = run_pytest(["-m", "real_drawing", "src/tests/test_real_drawings.py"],
                                  timeout=1800)
    if rc == 0:
        record("5-基线", "real_drawing 基线", "PASS",
               f"{passed} passed（Windows 参考: {_REFERENCE_REAL_DRAWING}）")
    else:
        record("5-基线", "real_drawing 基线", "FAIL", tail)


# ── 汇总 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--probes-only", action="store_true",
                        help="跳过阶段 4/5 pytest 回归，仅做快速漂移自检")
    args = parser.parse_args()

    print("BAA Linux CI 全量回归验证")
    print(f"  仓库: {ROOT}")

    # 阶段 0: 环境自检
    print("\n===== 阶段 0: 环境自检 =====")
    platform = sys.platform
    print(f"  python {sys.version.split()[0]} | platform={platform}")
    if not platform.startswith("linux"):
        print(f"  [WARN] 非 Linux 平台（{platform}）——阶段 2 按本机字体环境判定，阶段 3/4/5 结论仍有效")
    missing = []
    for mod in ("ezdxf", "reportlab", "pytest", "psutil"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        record("0-环境", "依赖完整性", "FAIL", f"缺失: {', '.join(missing)}（pip install -r requirements.txt）")
    else:
        record("0-环境", "依赖完整性", "PASS")

    stage_f1_static()
    stage_f1_runtime()
    stage_f2()
    if not args.probes_only:
        stage_full_suite()
        stage_real_drawing()

    # 汇总
    n_fail = sum(1 for r in RESULTS if r[2] == "FAIL")
    n_skip = sum(1 for r in RESULTS if r[2] == "SKIP")
    print("\n" + "=" * 62)
    print("验证结果汇总")
    print("=" * 62)
    for stage, name, status, detail in RESULTS:
        print(f"  {stage:<10} {name:<28} {status}")
    print("-" * 62)
    total = len(RESULTS)
    print(f"  合计 {total} 项: {total - n_fail - n_skip} PASS / {n_skip} SKIP / {n_fail} FAIL")
    if n_fail:
        print("\n结论: 存在回归漂移，请对照 docs/cross-platform-checklist-20261015.md 处置")
        return 1
    print("\n结论: 全部必选阶段通过，跨平台语义无漂移")
    return 0


if __name__ == "__main__":
    sys.exit(main())
