#!/usr/bin/env python3
"""
安全注释注入脚本 v2 — 更密集的注释策略

改进：
1. 对更多代码模式生成行内注释（return, raise, if/elif, for, with 等）
2. 对已有段首 # ── 注释的行，在代码行加行内注释
3. 使用 ast.Constant 兼容 Python 3.14
4. 保持语法安全（用 AST 验证）
"""

import ast
import sys
import re
import os


def should_skip(line: str) -> bool:
    """判断是否跳过此行"""
    stripped = line.strip()
    if not stripped:
        return True
    # docstring
    if stripped.startswith('"""') or stripped.startswith("'''"):
        return True
    # 纯注释行（已有完整注释）
    if stripped.startswith('#'):
        return True
    # import 语句
    if stripped.startswith('import ') or stripped.startswith('from '):
        return True
    # 装饰器
    if stripped.startswith('@'):
        return True
    # 函数/类定义
    if stripped.startswith('def ') or stripped.startswith('async def ') or stripped.startswith('class '):
        return True
    # 块起始关键字
    if stripped.startswith('try:') or stripped.startswith('finally:'):
        return True
    if stripped in ('pass', 'break', 'continue'):
        return True
    return False


def already_has_inline(line: str) -> bool:
    """检查是否已有行内注释"""
    stripped = line.strip()
    if '#' in stripped:
        idx = stripped.index('#')
        before = stripped[:idx].strip()
        if before:
            return True
    return False


# 行内注释映射
INLINE_COMMENTS = {
    'return ': '  # 返回',
    'raise ': '  # 抛出异常',
    'yield': '  # 生成',
    'if ': '  # 条件判断',
    'elif ': '  # 条件分支',
    'else:': '  # 否则',
    'for ': '  # 循环',
    'while ': '  # 循环',
    'with ': '  # 上下文管理',
    'except ': '  # 捕获异常',
    'break': '  # 跳出',
    'continue': '  # 继续',
}


def generate_comment(stripped: str) -> str:
    """根据代码行生成合适的行内注释"""
    # 匹配已知关键字
    for kw, comment in INLINE_COMMENTS.items():
        if stripped.startswith(kw):
            return comment

    # 赋值语句
    if '=' in stripped and not stripped.startswith('='):
        # 排除复合操作符
        lhs = stripped.split('=')[0].strip()
        if lhs and not any(kw in lhs for kw in ['if', 'for', 'while', 'and', 'or', 'not', 'in', 'is', 'lambda', 'else', 'elif']):
            # 检测赋值类型
            if '=' in stripped[len(lhs):].strip():
                return '  # 赋值'
    
    # 独立表达式/函数调用
    if re.match(r'^[a-zA-Z_][\w.]*(\(|\[)', stripped):
        return '  # 操作'
    
    # 字典/列表定义
    if stripped.startswith('{') or stripped.startswith('['):
        return '  # 定义'
    
    # return 类型注释（无值返回的）
    if stripped == 'return':
        return '  # 返回'

    return ''


def annotate_file(filepath: str):
    """安全地为文件添加行内注释"""
    with open(filepath) as f:
        lines = f.readlines()
    
    # 验证原始语法
    try:
        ast.parse(''.join(lines))
    except SyntaxError as e:
        print(f"原始文件语法错误: {e}")
        return 0
    
    # 找到所有字符串字面量的行号范围（避免污染）
    tree = ast.parse(''.join(lines))
    string_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            start_line = node.lineno
            end_line = getattr(node, 'end_lineno', start_line)
            for l in range(start_line, end_line + 1):
                string_lines.add(l)
    
    # 对每一行尝试添加注释
    added = 0
    modified_lines = []
    
    for i, line in enumerate(lines, 1):
        # 跳过字符串内部的行
        if i in string_lines:
            modified_lines.append(line)
            continue
        
        stripped = line.strip()
        
        # 跳过不应注释的行
        if should_skip(line):
            modified_lines.append(line)
            continue
        
        # 跳过已有行内注释的行
        if already_has_inline(line):
            modified_lines.append(line)
            continue
        
        comment = generate_comment(stripped)
        if comment:
            new_line = line.rstrip('\n') + comment + '\n'
            modified_lines.append(new_line)
            added += 1
            continue
        
        modified_lines.append(line)
    
    if added == 0:
        return 0
    
    # 验证修改后语法
    try:
        ast.parse(''.join(modified_lines))
    except SyntaxError as e:
        print(f"修改后语法错误: {e}")
        return -1
    
    # 写回文件
    with open(filepath, 'w') as f:
        f.writelines(modified_lines)
    
    return added


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 scripts/safe_annotate_v2.py <filepath>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"文件不存在: {filepath}")
        sys.exit(1)
    
    added = annotate_file(filepath)
    if added > 0:
        print(f"✅ 添加了 {added} 条行内注释")
    elif added == 0:
        print(f"⏭️  没有可添加的注释")
    else:
        print(f"❌ 语法错误，未写入")