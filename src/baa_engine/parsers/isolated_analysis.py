"""独立进程语义分析 — 防内存失控（T-opt31）.

在子进程中运行 SemanticAnalyzer.analyze()，父进程带超时等待。
超时后终止子进程，保护主进程/系统不被 OOM 拖垮。

关键设计：
- 子进程自行解析图纸（避免 pickle 序列化 RawPrimitive）
- 父进程仅传文件路径，结果通过管道回传
- 超时后 terminate/kill 子进程

状态码：
    ok         正常完成，结果已序列化回父进程
    timeout    软超时触发，子进程已终止
    memory_error  子进程 MemoryError（仍可能拖慢系统，但已被隔离）
    crash      子进程异常退出（非 MemoryError）
    no_result  管道关闭但未收到完整结果
"""
from __future__ import annotations

import multiprocessing as mp
import os
import pickle
import sys
import time
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# 超时配置（秒）
_SOFT_TIMEOUT_SEC = 300.0
# 超大图纸阈值（primitives 数），超过则强制走独立进程
_LARGE_DRAWING_THRESHOLD = 50000
# 子进程内存软上限（MB），超过则建议走独立进程
_MEMORY_LIMIT_MB = 512


@dataclass
class IsolatedResult:
    """独立进程分析结果."""

    status: str  # ok / timeout / memory_error / crash / no_result
    result: Optional[Dict[str, Any]] = None  # 正常结果
    error: Optional[str] = None  # 错误信息
    elapsed_sec: float = 0.0  # 子进程运行时长
    timed_out: bool = False  # 是否超时


def _worker_main(conn, dxf_path, max_entities, building_type, soft_timeout_sec):
    """子进程入口：解析图纸并运行语义分析，结果 pickle 序列化回管道."""
    import sys
    import os

    # 写诊断日志到文件（spawn 模式下 stdout/stderr 不可靠）
    log_path = os.path.join(os.path.dirname(dxf_path), "_worker_debug.log")
    def log(msg):
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{time.time():.1f}] {msg}\n")

    log(f"WORKER START pid={os.getpid()} dxf={dxf_path}")

    try:
        # 添加 src 目录到 sys.path
        _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        _src_dir = os.path.join(_project_root, "src")
        if _src_dir not in sys.path:
            sys.path.insert(0, _src_dir)
        log(f"sys.path[0]={sys.path[0]}")

        log("Importing DrawingParser...")
        from baa_engine.drawing_parser import DrawingParser
        log("Importing SemanticAnalyzer...")
        from baa_engine.semantic_analyzer import SemanticAnalyzer
        log("Imports OK")

        # 解析图纸
        log("Parsing drawing...")
        parser = DrawingParser()
        parse_result = parser.parse(dxf_path)
        primitives = parse_result.primitives
        dimensions = parse_result.dimensions
        block_refs = getattr(parse_result, "block_refs", None)
        log(f"Parsed: {len(primitives)} primitives, {len(dimensions)} dimensions")

        # 语义分析
        log("Running semantic analysis...")
        analyzer = SemanticAnalyzer()
        result = analyzer.analyze(
            primitives=primitives,
            dimensions=dimensions,
            max_entities=max_entities,
            building_type=building_type,
            dxf_path=dxf_path,
            block_refs=block_refs,
        )
        log(f"Analysis done: {len(result)} keys in result")

        # 序列化结果
        log("Serializing result...")
        data = pickle.dumps(result, protocol=4)
        log(f"Serialized: {len(data)} bytes, sending...")
        conn.send_bytes(data)
        log("Result sent OK")
    except MemoryError as e:
        log(f"MemoryError: {e}")
        conn.send_bytes(pickle.dumps({"_error": f"MemoryError: {e}"}))
    except Exception as e:
        tb = traceback.format_exc()
        log(f"Exception: {type(e).__name__}: {e}\n{tb}")
        conn.send_bytes(pickle.dumps({"_error": f"{type(e).__name__}: {e}\n{tb}"}))
    finally:
        conn.close()
        log("Worker done (finally)")


def analyze_isolated_file(
    dxf_path: str,
    max_entities: int = 10000,
    building_type: str = "civil",
    soft_timeout_sec: Optional[float] = None,
) -> IsolatedResult:
    """在独立子进程中解析图纸并执行语义分析，带超时保护.

    与 analyze_isolated() 不同，本函数让子进程自行解析图纸，
    避免父进程传 primitives（不可 pickle）。

    参数：
        dxf_path: DXF 文件路径
        max_entities: 最大处理实体数
        building_type: 建筑类型
        soft_timeout_sec: 软超时秒数，None 使用默认 300s

    返回 IsolatedResult：
        status == "ok"  → result 字段为分析结果 dict
        status == "timeout"  → timed_out=True，子进程已终止
        status == "memory_error"  → error 含 MemoryError 详情
        status == "crash"  → error 含异常栈
    """
    if soft_timeout_sec is None:
        soft_timeout_sec = _SOFT_TIMEOUT_SEC

    # Windows 下 spawn 模式；Linux/macOS 默认 fork
    ctx = mp.get_context("spawn" if os.name == "nt" else "fork")
    parent_conn, child_conn = ctx.Pipe(duplex=False)

    p = ctx.Process(
        target=_worker_main,
        args=(child_conn, dxf_path, max_entities, building_type, soft_timeout_sec),
        daemon=True,
    )
    # Windows 下子进程不显示控制台窗口
    if os.name == "nt":
        p._creationflags = 0x08000000  # CREATE_NO_WINDOW

    t0 = time.time()
    p.start()

    # 等待子进程完成或超时
    # 同时轮询管道，避免子进程 send_bytes 因缓冲区满而阻塞
    deadline = t0 + soft_timeout_sec
    exited = False
    early_data = None  # 子进程退出前收到的数据

    while time.time() < deadline:
        # 优先读取管道数据（防止子进程 send_bytes 阻塞）
        if parent_conn.poll(0.1):
            try:
                data = parent_conn.recv_bytes()
                early_data = pickle.loads(data)
                # 收到结果后等子进程退出
                p.join(5.0)
                exited = True
                break
            except (EOFError, pickle.UnpicklingError):
                pass

        if not p.is_alive():
            exited = True
            break
        time.sleep(0.1)

    elapsed = time.time() - t0

    if not exited:
        # 超时，终止子进程
        p.terminate()
        p.join(5.0)
        if p.is_alive():
            p.kill()
            p.join(1.0)
        return IsolatedResult(
            status="timeout",
            error=f"语义分析超过 {soft_timeout_sec}s 软超时，子进程已终止",
            elapsed_sec=elapsed,
            timed_out=True,
        )

    # 如果已在循环中收到结果，直接返回
    if early_data is not None:
        if isinstance(early_data, dict) and "_error" in early_data:
            err = early_data["_error"]
            if "MemoryError" in err:
                return IsolatedResult(status="memory_error", error=err, elapsed_sec=elapsed)
            return IsolatedResult(status="crash", error=err, elapsed_sec=elapsed)
        return IsolatedResult(status="ok", result=early_data, elapsed_sec=elapsed)

    # 子进程已退出，读取剩余数据
    messages = []
    while parent_conn.poll(0.5):
        try:
            data = parent_conn.recv_bytes()
            result = pickle.loads(data)
            messages.append(result)
        except (EOFError, pickle.UnpicklingError) as e:
            error = f"管道读取失败: {e}"
            if "MemoryError" in error:
                return IsolatedResult(status="memory_error", error=error, elapsed_sec=elapsed)
            return IsolatedResult(status="no_result", error=error, elapsed_sec=elapsed)

    if not messages:
        return IsolatedResult(status="no_result", error="子进程已退出但无结果", elapsed_sec=elapsed)

    # 取最后一条非空消息作为结果
    result_data = None
    for msg in reversed(messages):
        if isinstance(msg, dict) and len(msg) > 0:
            if "_error" in msg:
                err = msg["_error"]
                if "MemoryError" in err:
                    return IsolatedResult(status="memory_error", error=err, elapsed_sec=elapsed)
                return IsolatedResult(status="crash", error=err, elapsed_sec=elapsed)
            result_data = msg
            break

    if result_data is None:
        return IsolatedResult(status="no_result", error="子进程已退出但无有效结果", elapsed_sec=elapsed)

    return IsolatedResult(status="ok", result=result_data, elapsed_sec=elapsed)


# 兼容旧接口：analyze_isolated() 现在调用 analyze_isolated_file()
def analyze_isolated(
    primitives: List[Any],
    dimensions: Optional[List[Dict]] = None,
    max_entities: int = 10000,
    building_type: str = "civil",
    dxf_path: Optional[str] = None,
    block_refs: Optional[List[Dict]] = None,
    soft_timeout_sec: Optional[float] = None,
) -> IsolatedResult:
    """兼容旧接口（父进程传入 primitives）.

    注意：由于 spawn 模式下无法 pickle RawPrimitive，此接口会回退到
    非隔离模式（在父进程直接执行）。建议使用 analyze_isolated_file()。

    参数同 SemanticAnalyzer.analyze()，额外参数：
        soft_timeout_sec: 软超时秒数，None 使用默认 300s
    """
    # 检查是否有 dxf_path（新接口）
    if dxf_path and not primitives:
        return analyze_isolated_file(
            dxf_path=dxf_path,
            max_entities=max_entities,
            building_type=building_type,
            soft_timeout_sec=soft_timeout_sec,
        )

    # 回退：父进程直接执行（不隔离，但至少不会崩溃）
    from baa_engine.semantic_analyzer import SemanticAnalyzer

    analyzer = SemanticAnalyzer()
    result = analyzer.analyze(
        primitives=primitives,
        dimensions=dimensions,
        max_entities=max_entities,
        building_type=building_type,
        dxf_path=dxf_path,
        block_refs=block_refs,
    )
    return IsolatedResult(status="ok", result=result, elapsed_sec=0.0)


def is_large_drawing(primitives: List[Any]) -> bool:
    """判断是否为超大图纸，需要独立进程保护."""
    return len(primitives) > _LARGE_DRAWING_THRESHOLD


def should_use_isolated(primitives: List[Any]) -> bool:
    """根据图纸大小决定是否使用独立进程."""
    return is_large_drawing(primitives)


__all__ = [
    "IsolatedResult",
    "analyze_isolated",
    "analyze_isolated_file",
    "is_large_drawing",
    "should_use_isolated",
]