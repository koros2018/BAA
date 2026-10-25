"""T-C6 示例②：在线 SDK（启动 BAA 服务后 10 分钟内跑通）。

前置：
    1. 启动服务（任选其一）
       - docker compose up -d
       - uvicorn src.api.baa_api:app --port 8000
    2. 准备 API Key（未配置密钥的开发环境可先用任意非空串）

运行：
    BAA_API_KEY=your-key python src/sdk/examples/quickstart_online.py
    python src/sdk/examples/quickstart_online.py http://localhost:8000 your-key
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.sdk import BAAClient, BAAError  # noqa: E402


def main(argv: list[str]) -> int:
    base_url = argv[1] if len(argv) > 1 else os.getenv("BAA_BASE_URL", "http://localhost:8000")
    api_key = argv[2] if len(argv) > 2 else os.getenv("BAA_API_KEY", "")

    if not api_key:
        print("[ERROR] 缺少 API Key：设置 BAA_API_KEY 或作为第 2 个参数传入", file=sys.stderr)
        return 2

    client = BAAClient(api_key=api_key, base_url=base_url)

    try:
        print(f"[1/4] 健康检查 {base_url}")
        print(f"      {client.health()}")

        print("[2/4] 查询原子函数库")
        funcs = client.list_functions()
        print(f"      共 {funcs['count']} 条，示例: {funcs['functions'][0]['func_id']}")

        print("[3/4] 查询规范条文")
        specs = client.list_specs()
        standards = sorted({s["standard"] for s in specs["specs"]})
        print(f"      共 {specs['count']} 条，标准: {', '.join(standards)}")

        print("[4/4] 查询规范版本（T-C6 版本化）")
        versions = client.spec_versions()
        print(f"      支持标准: {', '.join(versions.get('standards', []))}")
    except BAAError as e:
        print(f"[ERROR] API 调用失败: {e}", file=sys.stderr)
        return 1

    print("\n[OK] 在线示例跑通")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
