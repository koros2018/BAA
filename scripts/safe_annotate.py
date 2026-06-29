#!/usr/bin/env python3
"""
安全注释注入脚本

策略：
1. 用 AST 解析源文件，找到所有非字符串/非docstring的代码行
2. 对符合条件的行添加行内注释（# ── 说明）
3. 每次修改后验证语法正确性
4. 避免污染字符串字面量和 docstring

用法：python3 scripts/safe_annotate.py <filepath>
"""

import ast
import sys
import re
import os


def get_line_comment(line: str, line_no: int) -> str:
    """根据代码内容生成合适的行内注释"""
    stripped = line.strip()
    
    # 已有行内注释的行跳过
    if '#' in stripped:
        idx = stripped.index('#')
        before = stripped[:idx].strip()
        if before:  # 已经有行内注释
            return ""
    
    # 空行或纯注释行跳过
    if not stripped or stripped.startswith('#'):
        return ""
    
    # docstring 行跳过
    if stripped.startswith('"""') or stripped.startswith("'''"):
        return ""
    
    # 根据模式匹配生成注释
    if stripped.startswith('import ') or stripped.startswith('from '):
        return ""
    
    if stripped.startswith('@'):
        return ""
    
    if stripped.startswith('def ') or stripped.startswith('async def '):
        return ""
    
    if stripped.startswith('class '):
        return ""
    
    if stripped.startswith('if ') or stripped.startswith('elif ') or stripped.startswith('else:'):
        return ""
    
    if stripped.startswith('for ') or stripped.startswith('while '):
        return ""
    
    if stripped.startswith('try:') or stripped.startswith('except ') or stripped.startswith('finally:'):
        return ""
    
    if stripped.startswith('with ') or stripped.startswith('async with '):
        return ""
    
    if stripped.startswith('return '):
        return ""
    
    if stripped.startswith('raise '):
        return ""
    
    if stripped.startswith('yield'):
        return ""
    
    if stripped.startswith('pass') or stripped.startswith('break') or stripped.startswith('continue'):
        return ""
    
    # 赋值语句
    if '=' in stripped and not stripped.startswith('='):
        var_part = stripped.split('=')[0].strip()
        if var_part and not any(kw in var_part for kw in ['if', 'for', 'while', 'and', 'or', 'not', 'in', 'is', 'lambda']):
            # 简单赋值
            if len(stripped) < 80:  # 不太长才加
                return "  # 赋值"
    
    # 函数调用（独立行）
    if re.match(r'^[a-zA-Z_][\w.]*\(', stripped):
        return "  # 调用"
    
    return ""


def safe_annotate(filepath: str, max_comments: int = 200):
    """安全地为文件添加行内注释"""
    with open(filepath) as f:
        lines = f.readlines()
    
    # 先验证原始语法
    try:
        ast.parse(''.join(lines))
    except SyntaxError as e:
        print(f"原始文件语法错误: {e}")
        return False
    
    # 找到 AST 中所有不在字符串/注释中的行
    tree = ast.parse(''.join(lines))
    
    # 收集所有可注释的行号（跳过字符串内部的）
    string_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Str):
            # 找到字符串所在的起始行
            start_line = node.lineno
            end_line = getattr(node, 'end_lineno', start_line)
            for l in range(start_line, end_line + 1):
                string_lines.add(l)
    
    # 对每一行尝试添加注释
    added = 0
    modified_lines = []
    
    for i, line in enumerate(lines, 1):
        if added >= max_comments:
            break
        
        # 跳过已经在字符串内部的行
        if i in string_lines:
            modified_lines.append(line)
            continue
        
        comment = get_line_comment(line, i)
        if comment:
            # 在行末添加注释（保留缩进）
            new_line = line.rstrip('\n') + comment + '\n'
            modified_lines.append(new_line)
            added += 1
            continue
        
        modified_lines.append(line)
    
    # 验证修改后语法
    try:
        ast.parse(''.join(modified_lines))
    except SyntaxError as e:
        print(f"修改后语法错误 (在第{added}个注释附近): {e}")
        # 回退到最后一个安全版本
        return False
    
    # 写回文件
    with open(filepath, 'w') as f:
        f.writelines(modified_lines)
    
    print(f"✅ 添加了 {added} 条行内注释")
    return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 scripts/safe_annotate.py <filepath>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"文件不存在: {filepath}")
        sys.exit(1)
    
    max_comments = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    safe_annotate(filepath, max_comments)
