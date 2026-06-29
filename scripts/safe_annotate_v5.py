#!/usr/bin/env python3
"""
安全注释注入脚本 v5 — 精确字符串检测

改进：只标记纯字符串文本的行（即 AST Constant 节点独占一行的情况），
而不是把包含字符串的整行都跳过。
"""

import ast
import sys
import re
import os


PATTERN_COMMENTS = [
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
    (r'^else:', '  # 否则'),
    # 赋值（支持类型注解）
    (r'^[a-zA-Z_][\w.]*(:\s*\w+)?\s*=', '  # 赋值'),
    # 函数/方法调用
    (r'^[a-zA-Z_][\w.]*\(', '  # 调用'),
    # 列表/字典/集合字面量
    (r'^\[', '  # 列表'),
    (r'^\{', '  # 字典/集合'),
    # 单独变量引用
    (r'^[a-zA-Z_][\w.]*$', '  # 引用'),
]


def generate_comment(stripped: str) -> str:
    for pattern, comment in PATTERN_COMMENTS:
        if re.match(pattern, stripped):
            return comment
    return ''


def is_pure_string_line(line: str, line_no: int, string_nodes: list) -> bool:
    """判断某行是否纯字符串文本行（docstring 内容行）"""
    s = line.strip()
    if not s:
        return False
    # 如果是三引号/docstring 起止行
    if s.startswith(('"""', "'''")):
        return True
    # 如果该行被 AST 标记为字符串常量独占一行
    for node, start, end in string_nodes:
        if start <= line_no <= end:
            if start == end == line_no:
                # 单行字符串：检查是否整行都是字符串
                stripped_no_quotes = s.strip('"\'').strip()
                if stripped_no_quotes and not any(kw in s for kw in ['=', 'return', 'if ', 'for ', 'while ', 'import ']):
                    # 看起来是 docstring 内容
                    return True
            else:
                # 多行字符串中的行
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
    
    # 收集所有字符串节点（ast.Constant 且值为 str）
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
        
        # 跳过空行
        if not stripped:
            modified_lines.append(line)
            continue
        
        # 跳过纯字符串文本行（docstring 内容）
        if is_pure_string_line(line, i, string_nodes):
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
        print("用法: python3 scripts/safe_annotate_v5.py <filepath>")
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