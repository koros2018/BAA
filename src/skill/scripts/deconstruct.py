#!/usr/bin/env python3
"""BAA 图纸解构（命令行工具）"""
import sys
import json
from baa_client import BAAClient


def main():
    if len(sys.argv) < 2:
        print("用法: python deconstruct.py <file_path> [building_type=civil|industrial]")
        sys.exit(1)

    file_path = sys.argv[1]
    building_type = sys.argv[2] if len(sys.argv) > 2 else "civil"

    client = BAAClient()
    result = client.deconstruct(file_path, building_type=building_type)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
