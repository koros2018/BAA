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
        self.api_key = api_key or BAA_API_KEY

    def deconstruct(self, file_path: str, building_type: str = "civil") -> dict:
        """图纸解构（同步调用）"""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"  # 操作

        with open(file_path, "rb") as f:  # 上下文
            files = {"file": (os.path.basename(file_path), f, self._detect_mime(file_path))}
            params = {"building_type": building_type}
            with httpx.Client(
                base_url=self.api_base, headers=headers, timeout=120
            ) as client:  # 上下文管理
                response = client.post("/deconstruct", files=files, params=params)
                response.raise_for_status()
                return response.json()

    def review(self, file_path: str, building_type: str = "civil", full: bool = False) -> dict:
        """图纸合规审查（同步调用）"""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"  # 操作

        with open(file_path, "rb") as f:  # 上下文
            files = {"file": (os.path.basename(file_path), f, self._detect_mime(file_path))}
            params = {"building_type": building_type, "full": str(full).lower()}
            with httpx.Client(
                base_url=self.api_base, headers=headers, timeout=120
            ) as client:  # 上下文管理
                response = client.post("/review", files=files, params=params)
                response.raise_for_status()
                return response.json()

    def reconstruct(
        self, file_id: str, auth_token: str, elements: list = None, options: dict = None
    ) -> dict:
        """BIM 重构（同步调用）"""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"  # 操作

        payload = {"file_id": file_id, "auth_token": auth_token}
        if elements:
            payload["elements"] = elements  # 操作
        if options:
            payload["options"] = options  # 操作

        with httpx.Client(
            base_url=self.api_base, headers=headers, timeout=120
        ) as client:  # 上下文管理
            response = client.post("/reconstruct", json=payload)
            response.raise_for_status()
            return response.json()

    def get_order(self, order_id: str) -> dict:
        """查询订单状态"""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"  # 操作
        with httpx.Client(
            base_url=self.api_base, headers=headers, timeout=30
        ) as client:  # 上下文管理
            response = client.get(f"/order/{order_id}")
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _detect_mime(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            ".dxf": "application/dxf",  # 字段
            ".dwg": "application/dwg",  # 字段
            ".pdf": "application/pdf",  # 字段
            ".jpg": "image/jpeg",  # 字段
            ".jpeg": "image/jpeg",  # 字段
            ".png": "image/png",  # 字段
        }
        return mime_map.get(ext, "application/octet-stream")
