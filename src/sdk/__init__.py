"""
BAA Python SDK — 轻量 HTTP 客户端

用法:
    from baa_sdk import BAAClient

    client = BAAClient(api_key="***", base_url="http://localhost:8000")

    # 审查图纸
    result = client.review("/path/to/drawing.dxf", standard="GB 50016-2014")
    print(result["structured_summary"]["top_violations"])

    # 解构图纸
    data = client.deconstruct("/path/to/drawing.dxf")
    print(data["entities"])

    # 查询审查历史
    history = client.review_history(limit=5)

    # 批量审查
    batch = client.batch_review(["a.dxf", "b.dxf"], standard="GB 50016-2014")

    # 多 Sheet 审查
    multi = client.review_multi_sheet("/path/to/drawing.dxf")

    # 热工 K 值反算
    k = client.thermal_k_value({"thickness": 0.12, "material": "concrete"})

    # 统计仪表盘
    stats = client.stats()

    # Webhook
    client.register_webhook({"url": "https://hook.example.com/notify", "events": ["review.done"]})
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

try:
    import httpx  # type: ignore
except ImportError:
    httpx = None  # 降级用 urllib


class BAAError(Exception):
    """BAA API 调用异常"""


class BAAClient:
    """BAA API 轻量客户端。

    支持标准库 fallback（httpx 可选），仅依赖 Python 标准库或 httpx。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        timeout: float = 300.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ── 内部 HTTP 层 ──────────────────────────────────────

    def _headers(self, content_type: Optional[str] = None) -> dict[str, str]:
        h = {"Authorization": f"Bearer ***", "User-Agent": "baa-sdk/1.0"}
        if content_type:
            h["Content-Type"] = content_type
        return h

    def _url(self, path: str, params: Optional[dict] = None) -> str:
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urlencode(params)
        return url

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        files: Optional[dict] = None,
        data: Optional[dict] = None,
    ) -> dict:
        """统一 HTTP 请求入口，优先 httpx，fallback 标准库 urllib。"""
        url = self._url(path, params)
        headers = self._headers()

        if httpx is not None:
            return self._request_httpx(method, url, headers, json_body, files, data)
        return self._request_urllib(method, url, headers, json_body, files, data)

    def _request_httpx(
        self,
        method: str,
        url: str,
        headers: dict,
        json_body: Optional[dict],
        files: Optional[dict],
        data: Optional[dict],
    ) -> dict:
        with httpx.Client(timeout=self.timeout) as client:
            if files:
                r = client.request(method, url, headers=headers, files=files, data=data)
            elif json_body is not None:
                r = client.request(method, url, headers=headers, json=json_body)
            else:
                r = client.request(method, url, headers=headers)
            r.raise_for_status()
            result = r.json()
            if result.get("status") == "error":
                raise BAAError(result.get("message", result.get("error_code", "unknown")))
            return result

    def _request_urllib(
        self,
        method: str,
        url: str,
        headers: dict,
        json_body: Optional[dict],
        files: Optional[dict],
        data: Optional[dict],
    ) -> dict:
        """标准库 fallback（无 httpx 时可用）。"""
        from urllib.request import Request, urlopen

        body: Optional[bytes] = None
        if json_body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        elif files:
            # 简单 multipart 实现
            boundary = "----BaaSdkBoundary"
            lines = []
            for field, fpath in files.items():
                fpath = Path(fpath)
                ctype = mimetypes.guess_type(str(fpath))[0] or "application/octet-stream"
                lines.append(f"--{boundary}".encode())
                lines.append(
                    f'Content-Disposition: form-data; name="{field}"; filename="{fpath.name}"'.encode()
                )
                lines.append(f"Content-Type: {ctype}".encode())
                lines.append(b"")
                lines.append(fpath.read_bytes())
            lines.append(f"--{boundary}--".encode())
            lines.append(b"")
            body = b"\r\n".join(lines)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"

        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=self.timeout) as resp:  # nosec
            raw = resp.read().decode("utf-8")
        result = json.loads(raw)
        if result.get("status") == "error":
            raise BAAError(result.get("message", result.get("error_code", "unknown")))
        return result

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        return self._request("GET", path, params=params)

    def _post(
        self,
        path: str,
        *,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        files: Optional[dict] = None,
        data: Optional[dict] = None,
    ) -> dict:
        """内部：打开文件对象后发请求，确保资源被正确释放。"""
        file_handles = []
        try:
            # httpx 要求 files 值为 (filename, file_obj, content_type) 三元组
            if files:
                wrapped = {}
                for field, fpath in files.items():
                    p = Path(fpath)
                    f = open(p, "rb")
                    file_handles.append(f)
                    ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
                    wrapped[field] = (p.name, f, ctype)
                files = wrapped
            return self._request(
                "POST", path, params=params, json_body=json_body, files=files, data=data
            )
        finally:
            for f in file_handles:
                try:
                    f.close()
                except Exception:
                    pass

    # ── 核心 API ──────────────────────────────────────────

    def health(self) -> dict:
        """健康检查"""
        return self._get("/health")

    def review(
        self,
        file_path: str,
        *,
        standard: str = "GB 50016-2014",
        building_type: str = "civil",
        full: bool = False,
    ) -> dict:
        """图纸合规审查（核心）"""
        path = Path(file_path)
        return self._post(
            "/review",
            params={"building_type": building_type, "standard": standard, "full": full},
            files={"file": str(path)},
        )

    def review_from_data(
        self,
        entities: list[dict],
        *,
        standard: str = "GB 50016-2014",
        building_type: str = "civil",
    ) -> dict:
        """从结构化实体数据直接审查（跳过图纸解析）"""
        return self._post(
            "/review-from-data",
            params={"building_type": building_type, "standard": standard},
            json_body={"entities": entities},
        )

    def deconstruct(
        self,
        file_path: str,
        *,
        standard: str = "GB 50016-2014",
        building_type: str = "civil",
    ) -> dict:
        """图纸解构"""
        path = Path(file_path)
        return self._post(
            "/deconstruct",
            params={"building_type": building_type, "standard": standard},
            files={"file": str(path)},
        )

    def batch_review(
        self,
        file_paths: list[str],
        *,
        standard: str = "GB 50016-2014",
        building_type: str = "civil",
    ) -> dict:
        """批量审查多份图纸"""
        files_dict = {f"files[{i}]": str(fp) for i, fp in enumerate(file_paths)}
        return self._post(
            "/batch-review",
            params={"building_type": building_type, "standard": standard},
            files=files_dict,
        )

    def reconstruct(self, data: dict) -> dict:
        """从结构化数据重建图纸"""
        return self._post("/reconstruct", json_body=data)

    # ── API v1 ────────────────────────────────────────────

    def list_functions(self) -> list[dict]:
        """列出所有原子函数"""
        return self._get("/api/v1/functions")

    def list_specs(self) -> list[dict]:
        """列出所有规范标准"""
        return self._get("/api/v1/specs")

    def update_function(self, func_id: str, body: dict) -> dict:
        """更新原子函数参数"""
        return self._post(f"/api/v1/functions/{func_id}/update", json_body=body)

    def reverse_generate(self, body: dict) -> dict:
        """反向重构（单房间 DXF 生成）"""
        return self._post("/api/v1/reverse", json_body=body)

    def reverse_generate_multi(self, body: dict) -> dict:
        """反向重构（多房间 DXF 生成）"""
        return self._post("/api/v1/reverse/multi", json_body=body)

    def correction_suggestions(self, file_id: str) -> list[dict]:
        """生成修正建议"""
        return self._post(
            "/api/v1/correction/suggestions",
            json_body={"file_id": file_id},
        )

    # ── 审查历史 / 队列 ───────────────────────────────────

    def review_history(self, limit: int = 10) -> list[dict]:
        """审查历史列表"""
        result = self._get("/review/history", params={"limit": limit})
        return result.get("history", result)

    def review_detail(self, review_id: str) -> dict:
        """审查详情"""
        return self._get(f"/review/history/{review_id}")

    def clear_review_history(self) -> dict:
        """清空审查历史"""
        return self._request("DELETE", "/review/history")

    def review_project_summary(self, file_ids: list[str]) -> dict:
        """项目级汇总（需提供文件 ID 列表）"""
        return self._get(
            "/review/project/summary",
            params={"file_ids": ",".join(file_ids)},
        )

    def review_queue_stats(self) -> dict:
        """审查队列统计（当前路由与 {task_id} 冲突，返回模拟数据）

        .. deprecated:: 使用 review_history() 替代。
        """
        # 后端 /review/queue/stats 被 /review/queue/{task_id} 路径匹配拦截
        # 此处跳过，调用方改用 review_history()
        return {"status": "ok", "note": "endpoint conflict; use review_history instead"}

    def review_queue_status(self, task_id: str) -> dict:
        """审查队列中某任务状态"""
        return self._get(f"/review/queue/{task_id}")

    def cancel_review_task(self, task_id: str) -> dict:
        """取消审查任务"""
        return self._request("DELETE", f"/review/queue/{task_id}")

    # ── 热工计算 ──────────────────────────────────────────

    def thermal_k_value(self, body: dict) -> dict:
        """热工 K 值反算"""
        return self._post("/thermal/k-value", json_body=body)

    # ── 渲染 ──────────────────────────────────────────────

    def render_drawing(self, file_id: str, overlay: bool = False) -> bytes:
        """渲染图纸（返回二进制）"""
        path = f"/render/{file_id}" + ("/overlay" if overlay else "")
        if httpx is not None:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(self._url(path), headers=self._headers())
                r.raise_for_status()
                return r.content
        from urllib.request import Request, urlopen

        req = Request(self._url(path), headers=self._headers())
        with urlopen(req, timeout=self.timeout) as resp:  # nosec
            return resp.read()

    # ── EMA2 / 第三方 ─────────────────────────────────────

    def create_ema2_task(self, body: dict) -> dict:
        """创建 EMA2 审查任务"""
        return self._post("/api/v1/tasks", json_body=body)

    def ema2_task_status(self, task_id: str) -> dict:
        """查询 EMA2 任务状态"""
        return self._get(f"/api/v1/tasks/{task_id}")

    def ema2_task_result(self, task_id: str) -> dict:
        """查询 EMA2 任务结果"""
        return self._get(f"/api/v1/tasks/{task_id}/result")

    # ── 施工图审查标准 (P48) ────────────────────────────────

    def list_construction_review_items(
        self,
        major: str = None,
        level: str = None,
        category: str = None,
        method: str = None,
    ) -> dict:
        """施工图审查深度标准列表

        可选过滤参数: major(level) / level(L1/L2/L3) / category / method
        """
        params = {
            k: v
            for k, v in {
                "major": major,
                "level": level,
                "category": category,
                "method": method,
            }.items()
            if v is not None
        }
        return self._get("/api/v1/construction-review", params=params)

    def construction_review_report(self, file_id: str) -> dict:
        """生成施工图审查深度评分报告"""
        return self._post(
            "/api/v1/construction-review/report",
            json_body={"file_id": file_id},
        )

    # ── 结构化导出 (P91) ────────────────────────────────────

    def export_review(self, review_id: str, format: str = "json") -> bytes:
        """导出审查结果为 JSON/CSV"""
        if httpx is not None:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(
                    self._url(f"/review/export", {"review_id": review_id, "format": format}),
                    headers=self._headers(),
                )
                r.raise_for_status()
                return r.content
        from urllib.request import Request, urlopen

        req = Request(
            self._url(f"/review/export?review_id={review_id}&format={format}"),
            headers=self._headers(),
        )
        with urlopen(req, timeout=self.timeout) as resp:  # nosec
            return resp.read()

    # ── 多 Sheet 审查 (P73) ────────────────────────────────

    def review_multi_sheet(
        self,
        file_path: str,
        *,
        standard: str = "GB 50016-2014",
        building_type: str = "civil",
    ) -> dict:
        """多 Sheet 图纸审查（每个 Layout 独立审查）"""
        path = Path(file_path)
        return self._post(
            "/api/v1/review-multi-sheet",
            params={"building_type": building_type, "standard": standard},
            files={"file": str(path)},
        )

    # ── 统计 / 仪表盘 (P72) ────────────────────────────────

    def stats(self) -> dict:
        """审查统计仪表盘"""
        return self._get("/api/v1/stats")

    # ── Webhook (P71) ──────────────────────────────────────

    def register_webhook(self, body: dict) -> dict:
        """注册 webhook 回调"""
        return self._post("/api/v1/admin/webhooks/register", json_body=body)

    def list_webhooks(self) -> list[dict]:
        """列出已注册 webhook"""
        return self._get("/api/v1/admin/webhooks")

    def delete_webhook(self, webhook_id: str) -> dict:
        """删除 webhook"""
        return self._request("DELETE", f"/api/v1/admin/webhooks/{webhook_id}")

    # ── 反馈闭环 ────────────────────────────────────────────

    def submit_feedback(self, body: dict) -> dict:
        """提交用户反馈（申诉/报告）"""
        return self._post("/api/v1/feedbacks", json_body=body)

    def list_feedbacks(self, status: str = "all", limit: int = 20) -> list[dict]:
        """列出反馈"""
        return self._get("/api/v1/feedbacks", params={"status": status, "limit": limit})

    def feedback_stats(self) -> dict:
        """反馈统计"""
        return self._get("/api/v1/feedbacks/stats")

    def review_feedback(self, feedback_id: str, body: dict) -> dict:
        """审核反馈"""
        return self._post(f"/api/v1/feedbacks/{feedback_id}/review", json_body=body)

    # ── 原子函数管理 ────────────────────────────────────────

    def adjust_threshold(self, func_id: str, threshold: float) -> dict:
        """调整原子函数阈值"""
        return self._post(
            "/api/v1/functions/adjust-threshold",
            json_body={"func_id": func_id, "threshold": threshold},
        )

    # ── 模型参数导出 (P93) ──────────────────────────────────

    def model_params_functions(
        self,
        category: str = None,
        limit: int = None,
    ) -> dict:
        """返回原子函数参数表"""
        return self._get(
            "/api/v1/model-params/functions",
            params={
                k: v for k, v in {"category": category, "limit": limit}.items() if v is not None
            },
        )

    def model_params_layer_rules(self) -> dict:
        """返回图层规则语义映射"""
        return self._get("/api/v1/model-params/layer-rules")

    def model_params_cd_items(self) -> dict:
        """返回施工图审查标准 (CD)"""
        return self._get("/api/v1/model-params/cd-items")

    def model_params_samples(self, limit: int = 500) -> dict:
        """返回审查样本 (SFT 三元组)"""
        return self._get("/api/v1/model-params/samples", params={"limit": limit})

    def model_params_spatial_graph(self) -> dict:
        """返回空间关系图"""
        return self._get("/api/v1/model-params/spatial-graph")

    def export_model_params(self, format: str = "json", limit: int = 500) -> bytes:
        """导出模型参数为 JSON / JSONL-SFT / HF Dataset / CSV"""
        params = {"format": format, "limit": limit}
        if httpx is not None:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(self._url("/api/v1/model-params/export", params), headers=self._headers())
                r.raise_for_status()
                return r.content
        from urllib.request import Request, urlopen

        req = Request(self._url("/api/v1/model-params/export", params), headers=self._headers())
        with urlopen(req, timeout=self.timeout) as resp:  # nosec
            return resp.read()

    # ── 审查任务 (EMA2) ─────────────────────────────────────

    def create_task(self, body: dict) -> dict:
        """创建审查任务（别名 create_ema2_task）"""
        return self._post("/api/v1/tasks", json_body=body)

    # ── 项目协作 (P43) ──────────────────────────────────────

    def collab_register(self, body: dict) -> dict:
        """注册协作用户"""
        return self._post("/api/v1/collab/register", json_body=body)

    def collab_login(self, body: dict) -> dict:
        """登录协作用户，返回 token"""
        return self._post("/api/v1/collab/login", json_body=body)

    def collab_create_team(self, token: str, body: dict) -> dict:
        """创建团队"""
        h = {"Authorization": f"Bearer {token}", "User-Agent": "baa-sdk/1.0"}
        if httpx is not None:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(self._url("/api/v1/collab/teams"), headers=h, json=body)
                r.raise_for_status()
                return r.json()
        from urllib.request import Request, urlopen

        req = Request(
            self._url("/api/v1/collab/teams"),
            data=json.dumps(body).encode("utf-8"),
            headers=h,
            method="POST",
        )
        with urlopen(req, timeout=self.timeout) as resp:  # nosec
            return json.loads(resp.read().decode("utf-8"))
