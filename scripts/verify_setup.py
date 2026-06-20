#!/usr/bin/env python3
"""
BAA 快速验证脚本 - 第1周地基验证
用法: python scripts/verify_setup.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def check_module(module_path: str, name: str) -> bool:
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, module_path)
        if spec and spec.loader:
            spec.loader.exec_module(spec.loader.create_module(spec))
            print(f"  ✅ {name}: 模块加载成功")
            return True
        print(f"  ❌ {name}: 模块加载失败")
        return False
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        return False


def main():
    print("=" * 50)
    print("BAA 第1周地基验证")
    print("=" * 50)

    # 1. 项目结构
    print("\n📁 项目结构:")
    required_dirs = [
        "src/baa_engine", "src/api", "src/frontend", "src/tests",
        "data/drawings/synthetic", "data/drawings/real", "data/models", "data/specs",
        "scripts", "docs",
    ]
    for d in required_dirs:
        path = os.path.join(os.path.dirname(__file__), "..", d)
        exists = os.path.isdir(path)
        print(f"  {'✅' if exists else '❌'} {d}")

    # 2. 核心模块
    print("\n🧩 核心模块:")
    base = os.path.join(os.path.dirname(__file__), "..", "src")
    modules = [
        (os.path.join(base, "baa_engine", "__init__.py"), "baa_engine"),
        (os.path.join(base, "baa_engine", "drawing_parser.py"), "drawing_parser"),
        (os.path.join(base, "baa_engine", "semantic_analyzer.py"), "semantic_analyzer"),
        (os.path.join(base, "baa_engine", "atomic_functions.py"), "atomic_functions"),
        (os.path.join(base, "baa_engine", "spec_repository.py"), "spec_repository"),
        (os.path.join(base, "baa_engine", "attribution_analyzer.py"), "attribution_analyzer"),
        (os.path.join(base, "api", "baa_api.py"), "baa_api"),
    ]
    for mod_path, name in modules:
        check_module(mod_path, name)

    # 3. 运行测试
    print("\n🧪 单元测试:")
    test_file = os.path.join(base, "tests", "test_engine.py")
    if os.path.exists(test_file):
        os.system(f"python3 {test_file}")

    print("\n" + "=" * 50)
    print("验证完成")
    print("=" * 50)


if __name__ == "__main__":
    main()