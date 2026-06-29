# scripts/baa_client.py
"""BAA API 客户端封装"""

import httpx
import json
import os
from config import BAA_API_BASE, BAA_API_KEY


class BAAClient:
    """BAA API 客户端"""

    def __init__(self, api_base: str = None, api_key: str = None):
        self.api_base = (api_base or BAA_API_BASE).rstrip("/")  # 赋值
        self.api_key = api_key or BAA_API_KEY  # 赋值

    def deconstruct(self, file_path: str, building_type: str = "civil") -> dict:
        """图纸解构（同步调用）"""
        headers = {}  # 赋值
        if self.api_key:  # 条件判断
            headers["Authorization"] = f"Bearer {self.api_key}"  # 操作

        with open(file_path, "rb") as f:  # 上下文
            files = {"file": (os.path.basename(file_path), f, self._detect_mime(file_path))}  # 赋值
            params = {"building_type": building_type}  # 赋值
            with httpx.Client(base_url=self.api_base, headers=headers, timeout=120) as client:  # 上下文管理
                response = client.post("/deconstruct", files=files, params=params)  # 赋值
                response.raise_for_status()  # 调用
                return response.json()  # 返回

    def review(self, file_path: str, building_type: str = "civil", full: bool = False) -> dict:
        """图纸合规审查（同步调用）"""
        headers = {}  # 赋值
        if self.api_key:  # 条件判断
            headers["Authorization"] = f"Bearer {self.api_key}"  # 操作

        with open(file_path, "rb") as f:  # 上下文
            files = {"file": (os.path.basename(file_path), f, self._detect_mime(file_path))}  # 赋值
            params = {"building_type": building_type, "full": str(full).lower()}  # 赋值
            with httpx.Client(base_url=self.api_base, headers=headers, timeout=120) as client:  # 上下文管理
                response = client.post("/review", files=files, params=params)  # 赋值
                response.raise_for_status()  # 调用
                return response.json()  # 返回

    def reconstruct(self, file_id: str, auth_token: str,
                    elements: list = None, options: dict = None) -> dict:  # 赋值
        """BIM 重构（同步调用）"""
        headers = {}  # 赋值
        if self.api_key:  # 条件判断
            headers["Authorization"] = f"Bearer {self.api_key}"  # 操作

        payload = {"file_id": file_id, "auth_token": auth_token}  # 赋值
        if elements:  # 条件判断
            payload["elements"] = elements  # 操作
        if options:  # 条件判断
            payload["options"] = options  # 操作

        with httpx.Client(base_url=self.api_base, headers=headers, timeout=120) as client:  # 上下文管理
            response = client.post("/reconstruct", json=payload)  # 赋值
            response.raise_for_status()  # 调用
            return response.json()  # 返回

    def get_order(self, order_id: str) -> dict:
        """查询订单状态"""
        headers = {}  # 赋值
        if self.api_key:  # 条件判断
            headers["Authorization"] = f"Bearer {self.api_key}"  # 操作
        with httpx.Client(base_url=self.api_base, headers=headers, timeout=30) as client:  # 上下文管理
            response = client.get(f"/order/{order_id}")  # 赋值
            response.raise_for_status()  # 调用
            return response.json()  # 返回

    @staticmethod
    def _detect_mime(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()  # 赋值
        mime_map = {  # 赋值
            ".dxf": "application/dxf",  # 字段
            ".dwg": "application/dwg",  # 字段
            ".pdf": "application/pdf",  # 字段
            ".jpg": "image/jpeg",  # 字段
            ".jpeg": "image/jpeg",  # 字段
            ".png": "image/png",  # 字段
        }  # 闭合
        return mime_map.get(ext, "application/octet-stream")  # 返回
