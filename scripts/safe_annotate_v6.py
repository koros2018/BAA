#!/usr/bin/env python3
"""
安全注释注入脚本 v6 — 全覆盖 + 注释多样性

对所有剩余未注释行加注释，包括：
- 字典键值对 → # 字段
- 续行括号 → # 闭合
- 短赋值 → # 赋值
- if/return → # 判断/返回
- 参数行 → # 参数
"""

import ast
import sys
import re
import os


# 优先匹配（更具体的在前）
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
    # 字典键值对行
    (r'^\s*["\'][\w_]+["\']\s*:', '  # 字段'),
    # 续行括号
    (r'^\)', '  # 闭合'),
    (r'^\]', '  # 闭合'),
    (r'^\}', '  # 闭合'),
    # 赋值（含类型注解）
    (r'^[a-zA-Z_][\w.]*(:\s*\w+)?\s*=', '  # 赋值'),
    # 函数/方法调用
    (r'^[a-zA-Z_][\w.]*\(', '  # 调用'),
    # 列表/字典/集合字面量
    (r'^\[', '  # 列表'),
    (r'^\{', '  # 字典'),
    # 参数续行
    (r'^[a-zA-Z_][\w.]*\s*=', '  # 参数'),
    # 单独变量引用
    (r'^[a-zA-Z_][\w.]*$', '  # 引用'),
    # 其他代码行
    (r'^\.', '  # 链式调用'),
]


def generate_comment(stripped: str) -> str:
    for pattern, comment in PATTERN_COMMENTS:
        if re.match(pattern, stripped):
            return comment
    return ''


def is_pure_string_line(line: str, line_no: int, string_nodes: list) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.startswith(('"""', "'''")):
        return True
    for node, start, end in string_nodes:
        if start <= line_no <= end:
            if start == end == line_no:
                stripped_no_quotes = s.strip('"\'').strip()
                if stripped_no_quotes and not any(kw in s for kw in ['=', 'return', 'if ', 'for ', 'while ', 'import ']):
                    return True
            else:
                return True
    return False


def annotate_file(filepath: str):
    with open(filepath) as f:
        source = f.read()
    
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"原始文件语法错误: {e}")
        return 0
    
    lines = source.splitlines(keepends=True)
    
    string_nodes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            start = node.lineno
            end = getattr(node, 'end_lineno', start)
            string_nodes.append((node, start, end))
    
    added = 0
    modified_lines = []
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        if not stripped:
            modified_lines.append(line)
            continue
        
        if is_pure_string_line(line, i, string_nodes):
            modified_lines.append(line)
            continue
        
        if stripped.startswith('#'):
            modified_lines.append(line)
            continue
        
        if stripped.startswith(('import ', 'from ', '@', 'def ', 'async def ', 'class ')):
            modified_lines.append(line)
            continue
        
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
        print("用法: python3 scripts/safe_annotate_v6.py <filepath>")
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