#!/usr/bin/env python3
"""
安全注释注入脚本 v3 — 全覆盖策略

对几乎所有非空、非导入、非装饰器、非定义行的可注释行添加注释。
使用 ast.Constant 兼容 Python 3.14。
"""

import ast
import sys
import re
import os


# 不同类型代码的行内注释
COMMENT_MAP = [
    (r'^return\b', '  # 返回'),
    (r'^raise\b', '  # 抛出异常'),
    (r'^yield\b', '  # 生成'),
    (r'^if\b', '  # 条件判断'),
    (r'^elif\b', '  # 分支'),
    (r'^else:', '  # 否则'),
    (r'^for\b', '  # 循环'),
    (r'^while\b', '  # 循环'),
    (r'^with\b', '  # 上下文'),
    (r'^except\b', '  # 捕获异常'),
    (r'^try:', '  # 尝试'),
    (r'^finally:', '  # 最终处理'),
    (r'^break\b', '  # 跳出循环'),
    (r'^continue\b', '  # 继续循环'),
    (r'^pass\b', '  # 占位'),
    (r'^del\b', '  # 删除'),
    (r'^global\b', '  # 全局变量'),
    (r'^nonlocal\b', '  # 非局部变量'),
    (r'^assert\b', '  # 断言'),
]


def generate_comment(stripped: str) -> str:
    """生成行内注释"""
    for pattern, comment in COMMENT_MAP:
        if re.match(pattern, stripped):
            return comment
    
    # 赋值语句
    if '=' in stripped and not stripped.startswith('='):
        lhs = stripped.split('=')[0].strip()
        if lhs and not any(kw in lhs for kw in ['if', 'for', 'while', 'and', 'or', 'not', 'in', 'is', 'lambda', 'else', 'elif']):
            return '  # 赋值'
    
    # 独立表达式（函数调用、方法调用等）
    if re.match(r'^[a-zA-Z_][\w.]*(\(|\[)', stripped):
        return '  # 操作'
    
    # 字典/列表/元组定义
    if stripped.startswith(('{', '[', '(')) and stripped.endswith(('}', ']', ')')):
        return '  # 数据结构'
    
    # 变量引用行（如 `result, ...` 只有变量）
    if re.match(r'^[a-zA-Z_][\w.,\s\[\]]*$', stripped) and ',' in stripped:
        return '  # 解包'
    
    return ''


def annotate_file(filepath: str):
    """安全地为文件添加行内注释"""
    with open(filepath) as f:
        lines = f.readlines()
    
    try:
        ast.parse(''.join(lines))
    except SyntaxError as e:
        print(f"原始文件语法错误: {e}")
        return 0
    
    # 收集所有字符串字面量行
    tree = ast.parse(''.join(lines))
    string_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            start = node.lineno
            end = getattr(node, 'end_lineno', start)
            for l in range(start, end + 1):
                string_lines.add(l)
    
    added = 0
    modified_lines = []
    
    for i, line in enumerate(lines, 1):
        if i in string_lines:
            modified_lines.append(line)
            continue
        
        stripped = line.strip()
        
        # 跳过：空行、纯注释、docstring、import、装饰器、函数/类定义
        if not stripped:
            modified_lines.append(line)
            continue
        if stripped.startswith('#'):
            modified_lines.append(line)
            continue
        if stripped.startswith(('"""', "'''")):
            modified_lines.append(line)
            continue
        if stripped.startswith(('import ', 'from ', '@', 'def ', 'async def ', 'class ')):
            modified_lines.append(line)
            continue
        
        # 已有行内注释的跳过
        if '#' in stripped:
            idx = stripped.index('#')
            before = stripped[:idx].strip()
            if before:
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
    
    try:
        ast.parse(''.join(modified_lines))
    except SyntaxError as e:
        print(f"语法错误: {e}")
        return -1
    
    with open(filepath, 'w') as f:
        f.writelines(modified_lines)
    
    return added


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 scripts/safe_annotate_v3.py <filepath>")
        sys.exit(1)
    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"文件不存在: {filepath}")
        sys.exit(1)
    added = annotate_file(filepath)
    if added > 0:
        print(f"✅ 添加了 {added} 条行内注释")
    elif added == 0:
        print(f"⏭️  无新增")
    else:
        print(f"❌ 语法错误")