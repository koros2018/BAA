"""T-C6 示例①：离线知识库包（无需启动服务，10 分钟内跑通）。

运行（在仓库根目录）：
    python src/sdk/examples/quickstart_offline.py

若包不存在，会自动调用服务端一键导出（`python -m src.baa_engine.knowledge`）。
也可显式指定包路径：
    python src/sdk/examples/quickstart_offline.py dist/baa_knowledge_v1.0.0.zip
"""

import sys
import zipfile
from pathlib import Path

# monorepo 内直接使用源码（安装后改为 `import baa_sdk`）
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.sdk import KnowledgeBundle, KnowledgeBundleError  # noqa: E402

DEFAULT_BUNDLE = ROOT / "dist" / "baa_knowledge_v1.0.0.zip"


def ensure_bundle(path: Path) -> Path:
    """包不存在时用服务端 CLI 一键导出。"""
    if path.exists():
        return path
    print(f"[1/3] 知识库包不存在，执行一键导出 -> {path}")
    from src.baa_engine.knowledge import write_bundle

    return write_bundle(path)


def main(argv: list[str]) -> int:
    bundle_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_BUNDLE
    try:
        bundle_path = ensure_bundle(bundle_path)

        print(f"[2/3] 加载并校验知识库包: {bundle_path}")
        kb = KnowledgeBundle.load(bundle_path)

        info = kb.summary()
        print(
            "      schema={schema_version} kb={kb_version} 生成于 {generated_at}".format(**info)
        )
        print(
            "      原子函数 {functions} 条 / 规范条文 {specs} 条 / 标准 {standards} 个".format(
                **info["counts"]
            )
        )
        print(f"      支持标准: {', '.join(info['standards'])}")

        print("[3/3] 查询示例")
        funcs = kb.functions
        sample = funcs[0]
        print(f"      原子函数示例: {sample['func_id']} - {sample['name']}（{sample['category']}）")
        print(f"        关联条款: {sample['clause_id']}  判定: {sample['operator']} {sample['threshold']}{sample['unit']}")

        grouped = kb.specs_by_standard()
        print(f"      规范分组: {', '.join(f'{k}={len(v)}' for k, v in sorted(grouped.items()))}")
        print(f"      版本元数据: {len(kb.versions.get('standards', []))} 个标准")
    except KnowledgeBundleError as e:
        print(f"[ERROR] 知识库包校验失败: {e}", file=sys.stderr)
        return 1
    except zipfile.BadZipFile as e:
        print(f"[ERROR] 不是有效的 zip 包: {e}", file=sys.stderr)
        return 1

    print("\n[OK] 离线示例跑通（全程无需网络与服务）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
