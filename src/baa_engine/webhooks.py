"""
P71 审查任务 Webhook 通知

任务完成后异步 POST 到指定 URL，支持 generic/飞书/钉钉 三种格式。
"""

import json
import time
import asyncio
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def build_webhook_payload(
    task_id: str,
    file_id: str,
    status: str,
    result: Optional[Dict[str, Any]],
    error: Optional[str],
    webhook_type: str = "generic",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构建 webhook payload

    Args:
        task_id: 任务 ID
        file_id: 文件 ID
        status: completed | failed
        result: 审查结果（已完成时）
        error: 错误信息（失败时）
        webhook_type: generic | feishu | dingtalk
        extra: 附加字段

    Returns:
        按 webhook_type 格式化的 payload
    """
    extra = extra or {}
    base = {
        "task_id": task_id,
        "file_id": file_id,
        "status": status,
        "completed_at": time.time(),
        **extra,
    }

    if webhook_type == "feishu":
        # 飞书 Bot Webhook 格式
        if status == "completed":
            title = f"✅ BAA 审查完成 — {file_id}"
            content = f"任务: {task_id}\n" f"状态: 已完成\n"
            # 添加摘要
            summary = result.get("summary", {}) if result else {}
            violations = summary.get("total_violations", 0)
            errors = summary.get("total_errors", 0)
            content += f"违规: {violations} | 错误: {errors}\n"
            content += f"耗时: {result.get('processing_time', 'N/A')}s" if result else ""
            return {
                "msg_type": "interactive",
                "card": {
                    "header": {"title": {"content": title, "tag": "plain_text"}},
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": content,
                        }
                    ],
                },
            }
        else:
            return {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"content": f"❌ BAA 审查失败 — {file_id}", "tag": "plain_text"}
                    },
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": f"任务: {task_id}\n错误: {error or 'Unknown'}",
                        }
                    ],
                },
            }

    if webhook_type == "dingtalk":
        # 钉钉 Markdown 格式
        if status == "completed":
            title = "BAA 审查完成"
            text = f"### {title}\n\n- 任务: `{task_id}`\n- 文件: `{file_id}`\n- 状态: 已完成\n"
            summary = result.get("summary", {}) if result else {}
            violations = summary.get("total_violations", 0)
            text += f"- 违规: {violations} | 错误: {summary.get('total_errors', 0)}\n"
            return {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
        else:
            return {
                "msgtype": "markdown",
                "markdown": {
                    "title": "BAA 审查失败",
                    "text": f"### ❌ BAA 审查失败\n\n- 任务: `{task_id}`\n- 文件: `{file_id}`\n- 错误: {error or 'Unknown'}",
                },
            }

    # generic: 通用 JSON
    if status == "completed" and result:
        base["result"] = result
    elif error:
        base["error"] = error
    return base


async def send_webhook(
    url: str,
    payload: Dict[str, Any],
    max_retries: int = 3,
    timeout: float = 10.0,
) -> bool:
    """异步 POST webhook，支持重试

    Args:
        url: Webhook URL
        payload: 请求体
        max_retries: 最大重试次数
        timeout: 单次请求超时秒数

    Returns:
        True 表示至少一次成功
    """
    import httpx

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    url, json=payload, headers={"Content-Type": "application/json"}
                )
                if resp.status_code < 500:
                    logger.info(f"Webhook sent to {url}: status={resp.status_code}")
                    return True
                # 5xx 可重试
                logger.warning(f"Webhook {url} returned {resp.status_code}, retrying...")
        except Exception as e:
            logger.error(f"Webhook {url} attempt {attempt+1}/{max_retries} failed: {e}")
        if attempt < max_retries - 1:
            await asyncio.sleep(2**attempt)  # 指数退避
    return False


def trigger_webhook(
    url: str,
    payload: Dict[str, Any],
    *,
    max_retries: int = 3,
    timeout: float = 10.0,
    _loop: Optional[asyncio.AbstractEventLoop] = None,
) -> Optional[asyncio.Task]:
    """同步触发异步 webhook 发送（不阻塞调用方）

    在非异步上下文中也会启动新事件循环来发送。
    """

    async def _send():
        return await send_webhook(url, payload, max_retries=max_retries, timeout=timeout)

    try:
        loop = _loop or asyncio.get_running_loop()
        return loop.create_task(_send())
    except RuntimeError:
        # 没有运行中的事件循环，直接同步发送
        try:
            return asyncio.run(_send())
        except Exception:
            logger.error("Webhook fallback send failed")
            return None
