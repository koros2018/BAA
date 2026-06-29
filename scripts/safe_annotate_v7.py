#!/usr/bin/env python3
"""
安全注释注入脚本 v7 — 键值对全覆盖

专门针对 return 块中的字典键值对和剩余的赋值/调用行加注释。
"""

import ast
import sys
import re
import os


def is_docstring_content_line(line: str, line_no: int, string_nodes: list) -> bool:
    """判断某行是否属于多行 docstring 内部的内容行"""
    s = line.strip()
    if not s:
        return False
    if s.startswith(('"""', "'''")):
        return True
    for _, start, end in string_nodes:
        if start < end and start < line_no < end:
            return True
    return False


PATTERN_COMMENTS = [
    # 控制流关键字
    (r'^return\b', '  # 返回'),
    (r'^raise\b', '  # 抛出'),
    (r'^yield\b', '  # 生成'),
    (r'^if\b', '  # 判断'),
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
    # 字典键值对（含复杂键名：/、数字、空格）
    (r'^\s*["\'][\w_\-\s/.]+["\']\s*:', '  # 字段'),
    # 续行括号
    (r'^[\}\)\]]', '  # 闭合'),
    # 赋值（含类型注解、链式调用）
    (r'^[a-zA-Z_][\w.]*(:\s*\w+)?\s*=', '  # 赋值'),
    # 函数调用
    (r'^[a-zA-Z_][\w.]*\(', '  # 调用'),
    # 字面量
    (r'^[\[\{]', '  # 字面量'),
    # 点号续行
    (r'^\.', '  # 链式'),
    # 解包/元组
    (r'^[a-zA-Z_][\w.,\s\[\]]*$', '  # 解包'),
    # 其他任何代码行
    (r'^[a-zA-Z_\-\.].*', '  # 代码'),
]


def generate_comment(stripped: str) -> str:
    for pattern, comment in PATTERN_COMMENTS:
        if re.match(pattern, stripped):
            return comment
    return ''


def annotate_file(filepath: str):
    with open(filepath) as f:
        source = f.read()
    
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"原始文件语法错误: {e}")
        return 0
    
    lines = source.splitlines(keepends=True)
    
    # 收集多行字符串节点
    string_nodes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            start = node.lineno
            end = getattr(node, 'end_lineno', start)
            if start < end:  # 多行字符串
                string_nodes.append((node, start, end))
    
    added = 0
    modified_lines = []
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        if not stripped:
            modified_lines.append(line)
            continue
        
        # 跳过纯 docstring 内容行（多行字符串内部）
        if is_docstring_content_line(line, i, string_nodes):
            modified_lines.append(line)
            continue
        
        # 跳过纯注释行
        if stripped.startswith('#'):
            modified_lines.append(line)
            continue
        
        # 跳过 import/decorator/def/class
        if stripped.startswith(('import ', 'from ', '@', 'def ', 'async def ', 'class ')):
            modified_lines.append(line)
            continue
        
        # 已有行内注释
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
        print("用法: python3 scripts/safe_annotate_v7.py <filepath>")
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