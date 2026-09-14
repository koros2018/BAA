#!/usr/bin/env python3
"""
BAA YOLO 数据训练管线统一入口（P137）

把分散的 5 个脚本编排成可断点续跑的流程：

    inventory  数据集资产盘点（scripts/data_inventory.py）
    annotate   自动标注（src/tools/auto_annotate_real.py）
    review     人工审核 UI（src/tools/annotate_ui.py，启动 streamlit）
    merge      合并/校验/split（scripts/merge_real_annotations.py）
    train      YOLO 训练（src/tools/p111_train_yolo.py）

用法：
    ./venv/bin/python scripts/train_pipeline.py inventory
    ./venv/bin/python scripts/train_pipeline.py annotate --all
    ./venv/bin/python scripts/train_pipeline.py review --dataset p84_yolo_dataset
    ./venv/bin/python scripts/train_pipeline.py merge --input-dir data/real_renderings
    ./venv/bin/python scripts/train_pipeline.py train
    ./venv/bin/python scripts/train_pipeline.py all            # 跑 inventory→merge→train（跳过人工审核）
    ./venv/bin/python scripts/train_pipeline.py status         # 显示流程状态与建议

设计原则：
- 每个 stage 独立可调，失败即停（不掩盖错误）
- 记录状态到 data/models/pipeline_state.json，支持断点续跑
- review 是交互式人工环节，`all` 模式跳过它并给出明确提示
- 依赖检查前置：缺 streamlit/ultralytics/PyMuPDF 时给出明确安装指引
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STATE_FILE = ROOT / "data" / "models" / "pipeline_state.json"

# stage -> (命令模板, 说明, 依赖模块名或 None)
STAGES = {
    "inventory": {
        "cmd": [sys.executable, "scripts/data_inventory.py"],
        "desc": "数据集资产盘点（图像/标签/孤儿标签/越界坐标）",
        "deps": ["yaml"],
        "interactive": False,
    },
    "annotate": {
        "cmd": [sys.executable, "src/tools/auto_annotate_real.py"],
        "desc": "DXF 真实图纸自动标注（渲染 + 语义实体转 YOLO 标签）",
        "deps": ["ezdxf", "numpy", "PIL"],
        "interactive": False,
        "needs_args": True,
    },
    "review": {
        "cmd": [sys.executable, "-m", "streamlit", "run", "src/tools/annotate_ui.py",
                "--server.port", "8501", "--server.headless", "true"],
        "desc": "人工审核/修正 UI（删误报·补漏检·改类别·导出 YOLO txt）",
        "deps": ["streamlit", "PIL", "yaml"],
        "interactive": True,
    },
    "merge": {
        "cmd": [sys.executable, "scripts/merge_real_annotations.py"],
        "desc": "真实标注整合（校验标签·train/val split·生成 data.yaml）",
        "deps": ["yaml"],
        "interactive": False,
    },
    "train": {
        "cmd": [sys.executable, "src/tools/p111_train_yolo.py"],
        "desc": "YOLO 训练（CPU；无 GPU 时预计数小时到数天）",
        "deps": ["ultralytics", "torch"],
        "interactive": False,
    },
}

STAGE_ORDER = ["inventory", "annotate", "review", "merge", "train"]

# 人工审核 UI 内置数据集（与 src/tools/annotate_ui.py 的 DEFAULT_DATASETS 一致）
REVIEW_DATASETS = ["p84_yolo_dataset", "p106_yolo_dataset/clean", "coco_v2_aug"]


def _check_deps(modules):
    """返回缺失的依赖名列表"""
    missing = []
    for mod in modules:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    return missing


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run_stage(stage, extra_args=None):
    spec = STAGES[stage]
    missing = _check_deps(spec["deps"])
    if missing:
        print(f"[{stage}] ❌ 缺少依赖: {', '.join(missing)}")
        print(f"           安装: {sys.executable} -m pip install {' '.join(missing)}")
        return False

    state = load_state()
    state.setdefault("history", [])
    state.setdefault("completed", [])

    cmd = list(spec["cmd"])
    if extra_args:
        cmd += list(extra_args)

    started = datetime.now()
    print(f"\n{'='*66}")
    print(f"[{stage}] {spec['desc']}")
    print(f"        开始: {started.strftime('%H:%M:%S')}")
    print(f"        命令: {' '.join(str(c) for c in cmd)}")
    print(f"{'='*66}")

    if spec.get("interactive"):
        print(f"[{stage}] 交互式环节 — 请在浏览器打开 Streamlit UI")
        print(f"          审核完成后关闭浏览器/终端，本步骤标记为手动完成")
        r = subprocess.run(cmd, cwd=ROOT)
    else:
        r = subprocess.run(cmd, cwd=ROOT)

    ended = datetime.now()
    elapsed = (ended - started).total_seconds()
    entry = {
        "stage": stage,
        "start": started.isoformat(timespec="seconds"),
        "end": ended.isoformat(timespec="seconds"),
        "elapsed_s": round(elapsed, 1),
        "returncode": r.returncode,
        "ok": r.returncode == 0,
    }
    state["history"].append(entry)
    state["last_run"] = entry
    if r.returncode == 0 and stage not in state["completed"]:
        state["completed"].append(stage)
    save_state(state)

    print(f"[{stage}] 结束: {elapsed:.1f}s  退出码: {r.returncode}  "
          f"{'✅ 成功' if r.returncode == 0 else '❌ 失败'}")
    return r.returncode == 0


def cmd_status(_args):
    state = load_state()
    print("=== BAA 数据训练管线状态 ===")
    print(f"状态文件: {STATE_FILE.relative_to(ROOT)}\n")
    print(f"{'stage':<12} {'类型':<10} {'状态':<8} 说明")
    print("-" * 72)
    completed = state.get("completed", [])
    for s in STAGE_ORDER:
        spec = STAGES[s]
        kind = "交互式" if spec["interactive"] else "自动"
        st = "✅ 完成" if s in completed else "⬜ 未跑"
        print(f"{s:<12} {kind:<10} {st:<8} {spec['desc']}")
    if state.get("history"):
        print(f"\n最近一次运行: {state['history'][-1]['stage']} "
              f"@ {state['history'][-1]['end']}  退出码 {state['history'][-1]['returncode']}")
    # 依赖检查
    print("\n依赖检查:")
    for s in STAGE_ORDER:
        miss = _check_deps(STAGES[s]["deps"])
        print(f"  {s:<12} {'❌ 缺 ' + ', '.join(miss) if miss else '✅ OK'}")
    # GPU 检查
    print("\n计算资源:")
    try:
        import torch
        if torch.cuda.is_available():
            print(f"  ✅ GPU: {torch.cuda.get_device_name(0)}")
        elif hasattr(torch, "xpu") and torch.xpu.is_available():
            print(f"  ✅ XPU: {torch.xpu.get_device_name(0)}")
        else:
            print("  ⚠️  仅 CPU — 训练耗时会数小时到数天")
    except ImportError:
        print("  ❌ torch 未安装")
    print(f"  CPU 核数: {__import__('multiprocessing').cpu_count()}")
    return 0


def cmd_all(args):
    """inventory → merge → train；review 是人工环节，跳过并提示"""
    print("⚠️  `all` 模式跳过 review（人工审核 UI），因为它是交互式环节。")
    print("   人工标注是 ground truth 的关键来源，建议单独运行：")
    print("     ./venv/bin/python scripts/train_pipeline.py review --dataset p84_yolo_dataset\n")
    for stage in ("inventory", "merge", "train"):
        if not run_stage(stage):
            print(f"\n❌ 管线在 {stage} 阶段失败，停止。修复后重跑："
                  f"\n   ./venv/bin/python scripts/train_pipeline.py {stage}")
            return 1
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="BAA YOLO 数据训练管线统一入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="stage", required=True)

    for name, spec in STAGES.items():
        p = sub.add_parser(name, help=spec["desc"])
        if name == "annotate":
            p.add_argument("--all", action="store_true", help="标注 data/ 下所有 DXF")
            p.add_argument("--dxf", help="单个 DXF 文件路径")
            p.add_argument("--output-dir", help="输出目录")
            p.add_argument("--dpi", type=int, help="渲染 DPI")
        elif name == "review":
            p.add_argument("--dataset", choices=REVIEW_DATASETS,
                           help="内置数据集名")
            p.add_argument("--dataset-root", help="自定义数据集根目录")
            p.add_argument("--split", default="train")
        elif name == "merge":
            p.add_argument("--input-dir", help="渲染图输入目录")
            p.add_argument("--output-dir", help="训练数据输出目录")
            p.add_argument("--val-ratio", type=float, default=0.2)
            p.add_argument("--seed", type=int, default=42)
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--min-objects", type=int)

    sub.add_parser("status", help="显示流程状态与依赖检查")
    sub.add_parser("all", help="inventory → merge → train（跳过人工审核）")

    args = parser.parse_args()

    if args.stage == "status":
        return cmd_status(args)
    if args.stage == "all":
        return cmd_all(args)

    # 其余 stage 转发已知参数
    extra = []
    for k, v in vars(args).items():
        if k in ("stage",):
            continue
        if v is None or v is False:
            continue
        flag = f"--{k.replace('_', '-')}"
        if isinstance(v, bool):
            extra.append(flag)
        else:
            extra += [flag, str(v)]

    ok = run_stage(args.stage, extra)
    if not ok:
        print(f"\n❌ `{args.stage}` 失败。修复后重跑，或运行 `status` 查看依赖。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
