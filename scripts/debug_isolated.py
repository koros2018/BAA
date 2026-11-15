"""调试独立进程分析结果."""
import multiprocessing as mp
import time
import sys
import os
import pickle
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def worker(conn, primitives_count):
    """子进程入口：打印诊断信息."""
    print(f"[子进程] 启动，primitives_count={primitives_count}", flush=True)
    try:
        # 添加 src 目录到 sys.path（关键修复）
        _project_src = os.path.join(PROJECT_ROOT, "src")
        if _project_src not in sys.path:
            sys.path.insert(0, _project_src)
        print(f"[子进程] sys.path[0]={sys.path[0]}", flush=True)

        from baa_engine.semantic_analyzer import SemanticAnalyzer
        print(f"[子进程] SemanticAnalyzer 已导入", flush=True)

        analyzer = SemanticAnalyzer()
        print(f"[子进程] SemanticAnalyzer 已实例化", flush=True)

        # 构造假数据
        fake_primitives = []
        fake_dimensions = []
        print(f"[子进程] 开始 analyze（{len(fake_primitives)} primitives）", flush=True)

        result = analyzer.analyze(
            primitives=fake_primitives,
            dimensions=fake_dimensions,
            max_entities=100,
        )
        print(f"[子进程] analyze 完成，结果类型: {type(result)}", flush=True)

        data = pickle.dumps(result, protocol=4)
        conn.send_bytes(data)
        print(f"[子进程] 结果已发送（{len(data)} bytes）", flush=True)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[子进程] 异常: {e}\n{tb}", flush=True)
        conn.send_bytes(pickle.dumps({"_error": str(e)}))
    finally:
        conn.close()
        print(f"[子进程] 管道已关闭", flush=True)

def main():
    print("[父进程] 启动", flush=True)
    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)

    p = ctx.Process(target=worker, args=(child_conn, 999), daemon=True)
    p.start()
    print(f"[父进程] 子进程 PID: {p.pid}", flush=True)

    # 等待 5 秒
    time.sleep(5)
    print(f"[父进程] 5秒后，子进程存活: {p.is_alive()}", flush=True)

    if parent_conn.poll(1.0):
        data = parent_conn.recv_bytes()
        print(f"[父进程] 收到 {len(data)} bytes", flush=True)
    else:
        print(f"[父进程] 未收到数据", flush=True)

    p.terminate()
    p.join(1.0)
    print(f"[父进程] 完成", flush=True)

if __name__ == "__main__":
    main()