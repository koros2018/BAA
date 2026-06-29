# scripts/baa_client.py
"""BAA API 客户端封装"""

import httpx
import json
import os
from config import BAA_API_BASE, BAA_API_KEY


class BAAClient:
    """BAA API 客户端"""

    def __init__(self, api_base: str = None, api_key: str = None):
        self.api_base = (api_base or BAA_API_BASE).rstrip("/")
        self.api_key = api_key or BAA_API_KEY  # 赋值

    def deconstruct(self, file_path: str, building_type: str = "civil") -> dict:
        """图纸解构（同步调用）"""
        headers = {}  # 赋值
        if self.api_key:  # 条件判断
            headers["Authorization"] = f"Bearer {self.api_key}"

        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, self._detect_mime(file_path))}
            params = {"building_type": building_type}
            with httpx.Client(base_url=self.api_base, headers=headers, timeout=120) as client:  # 上下文管理
                response = client.post("/deconstruct", files=files, params=params)
                response.raise_for_status()  # 调用
                return response.json()  # 返回

    def review(self, file_path: str, building_type: str = "civil", full: bool = False) -> dict:
        """图纸合规审查（同步调用）"""
        headers = {}  # 赋值
        if self.api_key:  # 条件判断
            headers["Authorization"] = f"Bearer {self.api_key}"

        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, self._detect_mime(file_path))}
            params = {"building_type": building_type, "full": str(full).lower()}
            with httpx.Client(base_url=self.api_base, headers=headers, timeout=120) as client:  # 上下文管理
                response = client.post("/review", files=files, params=params)
                response.raise_for_status()  # 调用
                return response.json()  # 返回

    def reconstruct(self, file_id: str, auth_token: str,
                    elements: list = None, options: dict = None) -> dict:
        """BIM 重构（同步调用）"""
        headers = {}  # 赋值
        if self.api_key:  # 条件判断
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {"file_id": file_id, "auth_token": auth_token}
        if elements:  # 条件判断
            payload["elements"] = elements
        if options:  # 条件判断
            payload["options"] = options

        with httpx.Client(base_url=self.api_base, headers=headers, timeout=120) as client:  # 上下文管理
            response = client.post("/reconstruct", json=payload)
            response.raise_for_status()  # 调用
            return response.json()  # 返回

    def get_order(self, order_id: str) -> dict:
        """查询订单状态"""
        headers = {}  # 赋值
        if self.api_key:  # 条件判断
            headers["Authorization"] = f"Bearer {self.api_key}"
        with httpx.Client(base_url=self.api_base, headers=headers, timeout=30) as client:  # 上下文管理
            response = client.get(f"/order/{order_id}")
            response.raise_for_status()  # 调用
            return response.json()  # 返回

    @staticmethod
    def _detect_mime(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()  # 赋值
        mime_map = {  # 赋值
            ".dxf": "application/dxf",
            ".dwg": "application/dwg",
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
        }
        return mime_map.get(ext, "application/octet-stream")
