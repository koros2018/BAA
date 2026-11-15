"""快速验证独立进程分析结果（单张图纸）."""
import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.parsers.isolated_analysis import analyze_isolated

def main():
    # 使用最小的图纸快速测试
    test_file = PROJECT_ROOT / "data" / "files" / "baa-file-030e6425d4fe.dxf"
    print(f"测试文件: {test_file}")
    print("=" * 60)

    parser = DrawingParser()
    r = parser.parse(str(test_file))
    print(f"primitives: {len(r.primitives):,}")

    # 测试独立进程分析
    print("\n[1] 测试独立进程分析...")
    t0 = time.time()
    iso_result = analyze_isolated(
        primitives=r.primitives,
        dimensions=r.dimensions,
        max_entities=100000,
        dxf_path=str(test_file),
        soft_timeout_sec=30.0,  # 30秒超时
    )
    elapsed = time.time() - t0

    print(f"  状态: {iso_result.status}")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  超时: {iso_result.timed_out}")
    if iso_result.error:
        print(f"  错误: {iso_result.error}")
    if iso_result.result:
        entities = iso_result.result.get("entities", [])
        print(f"  实体数: {len(entities):,}")

    if iso_result.status == "ok":
        print("\n✓ 独立进程分析成功！")
        return 0
    else:
        print(f"\n✗ 独立进程分析失败: {iso_result.status}")
        return 1

if __name__ == "__main__":
    sys.exit(main())