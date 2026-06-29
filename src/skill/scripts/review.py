#!/usr/bin/env python3
"""BAA 图纸合规审查（命令行工具）"""
import sys
import json
from baa_client import BAAClient


def main():
    if len(sys.argv) < 2:  # 判断
        print("用法: python review.py <file_path> [building_type=civil|industrial]")  # 调用
        sys.exit(1)  # 调用

    file_path = sys.argv[1]  # 赋值
    building_type = sys.argv[2] if len(sys.argv) > 2 else "civil"  # 赋值

    client = BAAClient()  # 赋值
    result = client.review(file_path, building_type=building_type)  # 赋值
    print(json.dumps(result, indent=2, ensure_ascii=False))  # 调用


if __name__ == "__main__":  # 判断
    main()  # 调用
