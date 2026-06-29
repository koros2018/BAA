#!/usr/bin/env python3
"""
安全注释注入脚本 v4 — 直接对每行剩余代码生成注释

策略：对每一行剩余未注释的代码，直接根据行首关键字匹配。
不依赖 = 号检测，而是直接模式匹配 + 白名单。
"""

import ast
import sys
import re
import os


# 行首模式 → 注释
PATTERN_COMMENTS = [
    # 控制流
    (r'^return\b', '  # 返回'),
    (r'^raise\b', '  # 抛出异常'),
    (r'^yield\b', '  # 生成'),
    (r'^if\b', '  # 条件判断'),
    (r'^elif\b', '  # 分支'),
    (r'^else:', '  # 否则'),
    (r'^for\b', '  # 遍历'),
    (r'^while\b', '  # 循环'),
    (r'^with\b', '  # 上下文'),
    (r'^except\b', '  # 捕获'),
    (r'^try:', '  # 尝试'),
    (r'^finally:', '  # 最终'),
    (r'^break\b', '  # 跳出'),
    (r'^continue\b', '  # 继续'),
    (r'^pass\b', '  # 占位'),
    (r'^del\b', '  # 删除'),
    (r'^assert\b', '  # 断言'),
    (r'^global\b', '  # 全局'),
    (r'^nonlocal\b', '  # 非局部'),
    # 赋值（变量名 = 表达式）
    (r'^[a-zA-Z_][\w.]*\s*=', '  # 赋值'),
    # 函数/方法调用
    (r'^[a-zA-Z_][\w.]*\(', '  # 调用'),
    # 列表/字典/集合字面量
    (r'^\[', '  # 列表'),
    (r'^\{', '  # 字典/集合'),
    # 元组解包
    (r'^[a-zA-Z_][\w.,\[\]\s]*=', '  # 解包'),
    # 变量引用（单独变量名作为表达式）
    (r'^[a-zA-Z_][\w.]*$', '  # 引用'),
]


def generate_comment(stripped: str) -> str:
    """生成行内注释"""
    for pattern, comment in PATTERN_COMMENTS:
        if re.match(pattern, stripped):
            return comment
    return ''


def annotate_file(filepath: str):
    """安全地为文件添加行内注释"""
    with open(filepath) as f:
        source = f.read()
    
    try:
        ast.parse(source)
    except SyntaxError as e:
        print(f"原始文件语法错误: {e}")
        return 0
    
    lines = source.splitlines(keepends=True)
    
    # 收集所有字符串字面量的行号
    tree = ast.parse(source)
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
        
        # 跳过空行
        if not stripped:
            modified_lines.append(line)
            continue
        
        # 跳过纯注释/docstring 行
        if stripped.startswith('#') or stripped.startswith(('"""', "'''")):
            modified_lines.append(line)
            continue
        
        # 跳过 import/decorator/def/class
        if stripped.startswith(('import ', 'from ', '@', 'def ', 'async def ', 'class ')):
            modified_lines.append(line)
            continue
        
        # 已有行内注释 → 跳过
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
        print("用法: python3 scripts/safe_annotate_v4.py <filepath>")
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