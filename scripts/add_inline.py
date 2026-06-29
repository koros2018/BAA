#!/usr/bin/env python3
"""
高效注释补充：在行末追加内联注释
目标：每行代码都有行内注释
"""
import re
import os
from pathlib import Path

ROOT = Path("/mnt/d/OpenClawData3workspace/Projects/BAA/src")

def has_inline_comment(line):
    """检查行末是否已有注释"""
    stripped = line.rstrip()
    if stripped.endswith("#"):
        return True
    # 检查是否有 # 注释（不在字符串内）
    in_string = False
    string_char = None
    for i, ch in enumerate(stripped):
        if ch in ('"', "'"):
            if not in_string:
                in_string = True
                string_char = ch
            elif ch == string_char:
                in_string = False
        elif ch == "#" and not in_string:
            if i > 0 and stripped[i-1].isspace():
                return True
    return False

def generate_inline_comment(line):
    """生成行末内联注释"""
    s = line.strip()
    if not s or s.startswith("#") or s.startswith(("import ", "from ")):
        return None
    
    code = s.split(" #")[0].strip() if " #" in s else s
    
    # 结构型
    if code.startswith("class ") and ":" in code:
        m = re.match(r"class (\w+)", code)
        return f" # 类定义: {m.group(1)}" if m else " # 类定义"
    
    if code.startswith("def ") and "(" in code:
        m = re.match(r"def (\w+)", code)
        if m:
            name = m.group(1)
            if name.startswith("__"):
                return f" # 内部方法: {name}"
            return f" # 函数定义: {name}"
    
    if code.startswith("return ") and len(code) > 7:
        return " # 返回结果"
    if code == "return":
        return " # 返回 None"
    if code.startswith("raise "):
        return " # 抛出异常"
    if code == "pass":
        return " # 空实现"
    if code == "break":
        return " # 中断"
    if code == "continue":
        return " # 继续"
    if code.startswith("if ") and ":" in code:
        return " # 条件判断"
    if code.startswith("elif ") and ":" in code:
        return " # 条件分支"
    if code == "else:":
        return " # 否则分支"
    if code.startswith("for ") and ":" in code:
        return " # 循环遍历"
    if code.startswith("while ") and ":" in code:
        return " # 条件循环"
    if code == "try:":
        return " # 异常捕获"
    if code.startswith("except"):
        return " # 异常处理"
    if code.startswith("with "):
        return " # 上下文管理"
    
    # 操作型
    if " is None " in code or code.endswith(" is None"):
        return " # 空值检查"
    if " is not None" in code:
        return " # 非空检查"
    if ".append(" in code:
        return " # 追加元素"
    if ".get(" in code:
        return " # 安全获取值"
    if ".pop(" in code:
        return " # 弹出元素"
    if ".items()" in code:
        return " # 遍历键值对"
    if ".keys()" in code:
        return " # 遍历键"
    if ".values()" in code:
        return " # 遍历值"
    if "sorted(" in code:
        return " # 排序"
    if "enumerate(" in code:
        return " # 枚举获取索引"
    if "isinstance(" in code:
        return " # 类型检查"
    if "json." in code:
        if ".dumps" in code: return " # JSON 序列化"
        if ".loads" in code: return " # JSON 反序列化"
        if ".dump" in code: return " # JSON 写入"
        if ".load" in code: return " # JSON 读取"
        return " # JSON 处理"
    if "os." in code:
        if ".getenv" in code: return " # 获取环境变量"
        if ".makedirs" in code: return " # 创建目录"
        if ".exists" in code: return " # 检查存在性"
        if ".remove" in code or ".unlink" in code: return " # 删除文件"
        return " # 系统操作"
    if "Path(" in code:
        return " # 路径对象"
    if "asyncio." in code:
        return " # 异步操作"
    if "await " in code:
        return " # 异步等待"
    if "." in code and "(" in code:
        m = re.search(r"\.(\w+)\(", code)
        if m:
            method = m.group(1)
            if method in ("get", "post", "put", "delete", "patch"):
                return f" # HTTP {method.upper()}"
            if method in ("split", "join", "strip", "replace", "find", "startswith", "endswith"):
                return " # 字符串操作"
            if method in ("append", "extend", "pop", "remove", "insert"):
                return " # 列表操作"
            if method in ("items", "keys", "values", "get", "update", "setdefault"):
                return " # 字典操作"
    
    if "=" in code and "==" not in code and "!=" not in code:
        return " # 赋值"
    if any(op in code for op in [" == ", " != ", " > ", " < ", " >= ", " <= "]):
        return " # 比较运算"
    if " and " in code or " or " in code or " not " in code:
        return " # 逻辑运算"
    if " + " in code or " - " in code or " * " in code or " / " in code:
        return " # 数值运算"
    
    return None

def process_file(filepath: Path) -> int:
    with open(filepath) as f:
        lines = f.readlines()
    
    new_lines = []
    added = 0
    
    for line in lines:
        stripped = line.rstrip()
        
        # 只处理有实际代码且无行末注释的行
        if stripped and not stripped.endswith("#") and not stripped.startswith(("#", '"""', "'''", "import ", "from ")):
            # 检查是否需要加注释
            if not has_inline_comment(line):
                comment = generate_inline_comment(line)
                if comment:
                    new_lines.append(stripped + comment + "\n")
                    added += 1
                    continue
        
        new_lines.append(line)
    
    with open(filepath, "w") as f:
        f.writelines(new_lines)
    return added

# === 执行 ===
total = 0
for root, dirs, files in os.walk(ROOT):
    for f in sorted(files):
        if not f.endswith(".py") or "__pycache__" in root:
            continue
        path = Path(root) / f
        added = process_file(path)
        if added > 0:
            total += added
            comments = sum(1 for l in open(path) if l.strip().startswith("#") or l.strip().startswith('"""'))
            lines = sum(1 for _ in open(path))
            pct = comments * 100 / lines if lines > 0 else 0
            print(f"{str(path.relative_to(ROOT)):50s} +{added:4d} → {pct:.1f}%")

print(f"\n总新增: {total}")
