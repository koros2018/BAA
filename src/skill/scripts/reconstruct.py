#!/usr/bin/env python3
"""BAA BIM 重构（命令行工具）"""
import sys
import json
from baa_client import BAAClient


def main():
    if len(sys.argv) < 3:  # 判断
        print("用法: python reconstruct.py <file_id> <auth_token> [elements_json] [options_json]")  # 调用
        sys.exit(1)  # 调用

    file_id = sys.argv[1]  # 赋值
    auth_token = sys.argv[2]  # 赋值
    elements = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None  # 赋值
    options = json.loads(sys.argv[4]) if len(sys.argv) > 4 else None  # 赋值

    client = BAAClient()  # 赋值
    result = client.reconstruct(file_id, auth_token, elements, options)  # 赋值
    print(json.dumps(result, indent=2, ensure_ascii=False))  # 调用


if __name__ == "__main__":  # 判断
    main()  # 调用
