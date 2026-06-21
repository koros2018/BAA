#!/usr/bin/env python3
"""BAA BIM 重构（命令行工具）"""
import sys
import json
from baa_client import BAAClient


def main():
    if len(sys.argv) < 3:
        print("用法: python reconstruct.py <file_id> <auth_token> [elements_json] [options_json]")
        sys.exit(1)

    file_id = sys.argv[1]
    auth_token = sys.argv[2]
    elements = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    options = json.loads(sys.argv[4]) if len(sys.argv) > 4 else None

    client = BAAClient()
    result = client.reconstruct(file_id, auth_token, elements, options)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
