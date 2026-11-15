"""调试真实图纸分析."""
import multiprocessing as mp
import time
import sys
import os
import pickle
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def worker(conn, dxf_path):
    """子进程入口."""
    print(f"[子进程] 启动，dxf_path={dxf_path}", flush=True)
    try:
        # 添加 src 目录到 sys.path
        _src_dir = os.path.join(PROJECT_ROOT, "src")
        if _src_dir not in sys.path:
            sys.path.insert(0, _src_dir)
        print(f"[子进程] sys.path[0]={sys.path[0]}", flush=True)

        from baa_engine.drawing_parser import DrawingParser
        from baa_engine.semantic_analyzer import SemanticAnalyzer
        print(f"[子进程] 模块已导入", flush=True)

        # 解析图纸
        print(f"[子进程] 开始解析图纸...", flush=True)
        parser = DrawingParser()
        r = parser.parse(str(dxf_path))
        print(f"[子进程] 解析完成，primitives={len(r.primitives)}", flush=True)

        # 语义分析
        print(f"[子进程] 开始语义分析...", flush=True)
        analyzer = SemanticAnalyzer()
        result = analyzer.analyze(
            primitives=r.primitives,
            dimensions=r.dimensions,
            max_entities=100000,
            dxf_path=str(dxf_path),
        )
        print(f"[子进程] 语义分析完成，结果类型: {type(result)}", flush=True)

        data = pickle.dumps(result, protocol=4)
        conn.send_bytes(data)
        print(f"[子进程] 结果已发送（{len(data)} bytes）", flush=True)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[子进程] 异常: {e}\n{tb}", flush=True)
        conn.send_bytes(pickle.dumps({"_error": str(e)}))
    finally:
        conn.close()
        print(f"[子进程] 管道已关闭", flush=True)

def main():
    test_file = PROJECT_ROOT / "data" / "files" / "baa-file-030e6425d4fe.dxf"
    print(f"[父进程] 启动，测试文件: {test_file}", flush=True)

    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)

    p = ctx.Process(target=worker, args=(child_conn, test_file), daemon=True)
    p.start()
    print(f"[父进程] 子进程 PID: {p.pid}", flush=True)

    # 等待子进程完成（最多 30 秒）
    deadline = time.time() + 30
    exited = False

    while time.time() < deadline:
        if not p.is_alive():
            exited = True
            break
        time.sleep(0.5)

    if exited:
        print(f"[父进程] 子进程已退出", flush=True)
    else:
        print(f"[父进程] 超时，终止子进程", flush=True)
        p.terminate()
        p.join(1.0)

    # 读取所有数据
    messages = []
    while parent_conn.poll(1.0):
        try:
            data = parent_conn.recv_bytes()
            result = pickle.loads(data)
            messages.append(result)
            print(f"[父进程] 收到消息 #{len(messages)}: {type(result)}", flush=True)
        except Exception as e:
            print(f"[父进程] 读取失败: {e}", flush=True)
            break
    print(f"[父进程] 共收到 {len(messages)} 条消息", flush=True)

if __name__ == "__main__":
    main()