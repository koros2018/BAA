"""独立进程语义分析 — 防内存失控（T-opt31）.

在子进程中运行 SemanticAnalyzer.analyze()，父进程带超时等待。
超时后终止子进程，保护主进程/系统不被 OOM 拖垮。

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
_SOFT_TIMEOUT_SEC = 240.0
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


def _worker_main(conn, primitives, dimensions, max_entities, building_type, dxf_path, block_refs):
    """子进程入口：运行语义分析，结果 pickle 序列化回管道."""
    try:
        # 延迟导入，避免子进程启动时加载全部依赖
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
        # 序列化结果（pickle 协议 4，兼容 Python 3.4+）
        data = pickle.dumps(result, protocol=4)
        conn.send_bytes(data)
    except MemoryError as e:
        conn.send_bytes(pickle.dumps({"_error": f"MemoryError: {e}"}))
    except Exception as e:
        tb = traceback.format_exc()
        conn.send_bytes(pickle.dumps({"_error": f"{type(e).__name__}: {e}\n{tb}"}))
    finally:
        conn.close()


def analyze_isolated(
    primitives: List[Any],
    dimensions: Optional[List[Dict]] = None,
    max_entities: int = 10000,
    building_type: str = "civil",
    dxf_path: Optional[str] = None,
    block_refs: Optional[List[Dict]] = None,
    soft_timeout_sec: Optional[float] = None,
) -> IsolatedResult:
    """在独立子进程中执行语义分析，带超时保护.

    参数与 SemanticAnalyzer.analyze() 一致，额外参数：
        soft_timeout_sec: 软超时秒数，None 使用默认 240s

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
        args=(child_conn, primitives, dimensions, max_entities, building_type, dxf_path, block_refs),
        daemon=True,
    )
    # Windows 下子进程不显示控制台窗口
    if os.name == "nt":
        p._creationflags = 0x08000000  # CREATE_NO_WINDOW

    t0 = time.time()
    p.start()

    # 等待子进程完成或超时
    # 先等待一小段时间看子进程是否快速失败
    if parent_conn.poll(0.1):
        # 子进程已发送数据或异常
        pass
    else:
        # 继续等待，直到超时
        remaining = soft_timeout_sec
        while remaining > 0:
            if parent_conn.poll(0.5):
                break
            if not p.is_alive():
                break
            time.sleep(0.5)
            remaining -= 0.5

    elapsed = time.time() - t0

    # 判断状态
    if p.is_alive():
        # 子进程仍在运行 → 超时
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

    # 子进程已结束，读取结果
    if parent_conn.poll(1.0):
        try:
            data = parent_conn.recv_bytes()
            result = pickle.loads(data)
            if isinstance(result, dict) and "_error" in result:
                err = result["_error"]
                if "MemoryError" in err:
                    return IsolatedResult(status="memory_error", error=err, elapsed_sec=elapsed)
                return IsolatedResult(status="crash", error=err, elapsed_sec=elapsed)
            return IsolatedResult(status="ok", result=result, elapsed_sec=elapsed)
        except (EOFError, pickle.UnpicklingError) as e:
            return IsolatedResult(status="no_result", error=f"管道读取失败: {e}", elapsed_sec=elapsed)
    else:
        return IsolatedResult(status="no_result", error="子进程结束但未返回结果", elapsed_sec=elapsed)


def is_large_drawing(primitives: List[Any]) -> bool:
    """判断是否为超大图纸，需要独立进程保护."""
    return len(primitives) > _LARGE_DRAWING_THRESHOLD


def should_use_isolated(primitives: List[Any]) -> bool:
    """根据图纸大小决定是否使用独立进程."""
    return is_large_drawing(primitives)


__all__ = [
    "IsolatedResult",
    "analyze_isolated",
    "is_large_drawing",
    "should_use_isolated",
]