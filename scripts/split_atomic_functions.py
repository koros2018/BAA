#!/usr/bin/env python3
"""
P7 原子函数模块化拆分 - 自动生成脚本
用法: python3 scripts/split_atomic_functions.py
从 atomic_functions.py 解析所有 AtomicFunction 定义，按规范分组输出到 atomic/ 子目录。
"""
import ast
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(SCRIPT_DIR, "..")
PY_FILE = os.path.join(REPO_ROOT, "src/baa_engine/atomic_functions.py")
OUT_DIR = os.path.join(REPO_ROOT, "src/baa_engine/atomic")

# GB 规范前缀 → 输出文件名
FILE_MAP = {
    "GB50016-": "fire_general.py",   # 通用消防 GB50016
    "GB50067-": "fire_general.py",   # 车库消防 GB50067，归入通用消防
    "GB50974-": "fire_sprinkler.py", # 自动喷水灭火 GB50974
    "GB50116-": "fire_alarm.py",     # 火灾自动报警 GB50116
    "GB50763-": "accessibility.py",  # 无障碍 GB50763
}


def parse_atomic_functions():
    """解析 atomic_functions.py，提取所有 AtomicFunction 实例化调用。"""
    with open(PY_FILE) as f:
        content = f.read()

    tree = ast.parse(content)

    func_defs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FuncRegistry":
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        name = target.id if isinstance(target, ast.Name) else "?"
                        if isinstance(item.value, ast.List) and "FUNCS" in name:
                            for elt in item.value.elts:
                                if isinstance(elt, ast.Call):
                                    func_id = None
                                    clause_id = None
                                    # 优先从 positional args 取 (func_id=arg[0], clause_id=arg[3])
                                    if len(elt.args) >= 4:
                                        if isinstance(elt.args[0], ast.Constant):
                                            func_id = elt.args[0].value
                                        if isinstance(elt.args[3], ast.Constant):
                                            clause_id = elt.args[3].value
                                    # 再从 keyword args 补
                                    for kw in elt.keywords:
                                        if kw.arg == "func_id" and isinstance(kw.value, ast.Constant):
                                            func_id = kw.value.value
                                        if kw.arg == "clause_id" and isinstance(kw.value, ast.Constant):
                                            clause_id = kw.value.value

                                    if func_id and clause_id:
                                        gb_prefix = clause_id[:8]
                                        file_name = FILE_MAP.get(gb_prefix, "building_basic.py")
                                        func_defs.append({
                                            "func_id": func_id,
                                            "clause_id": clause_id,
                                            "gb_prefix": gb_prefix,
                                            "file": file_name,
                                            "node": elt,
                                            "source_list": name,
                                        })

    return func_defs


def generate_module_file(file_name, funcs):
    """为某组原子函数生成模块文件内容。"""
    lines = []
    label = file_name.replace(".py", "").replace("_", " ").title()
    lines.append('"""')
    lines.append(f"BAA 原子函数 - {label}")
    lines.append(f"共 {len(funcs)} 条原子函数")
    lines.append('"')
    lines.append("")
    lines.append("from ..atomic_functions import (  # import from parent")
    lines.append("    AtomicFunction,")
    lines.append("    FuncCategory,")
    lines.append(")")
    lines.append("")
    lines.append(f"MODULE_FUNCS = [  # module-level atomic function registry")
    lines.append("")

    # 按 func_id 去重（保留首次出现）
    seen_ids = set()
    for func in funcs:
        fid = func["func_id"]
        if fid in seen_ids:
            continue
        seen_ids.add(fid)
        node = func["node"]
        # 用 ast.unparse 生成可执行代码，保真度最高
        code = ast.unparse(node)
        lines.append(code + ",")

    lines.append("]  # type: ignore[name-defined]")
    lines.append("")
    return "\n".join(lines)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    funcs = parse_atomic_functions()
    print(f"Parsed {len(funcs)} atomic function definitions")

    # 按目标文件分组
    by_file = defaultdict(list)
    for f in funcs:
        by_file[f["file"]].append(f)

    seen_prefixes = set(f["gb_prefix"] for f in funcs)
    print(f"GB prefixes found: {sorted(seen_prefixes)}")

    for file_name, items in sorted(by_file.items()):
        content = generate_module_file(file_name, items)
        out_path = os.path.join(OUT_DIR, file_name)
        with open(out_path, "w") as f:
            f.write(content)
        unique_ids = len(set(i["func_id"] for i in items))
        print(f"  {file_name}: {len(items)} entries, {unique_ids} unique -> {out_path}")

    print("\nDone! Next: create atomic/__init__.py and update atomic_functions.py")


if __name__ == "__main__":
    main()
