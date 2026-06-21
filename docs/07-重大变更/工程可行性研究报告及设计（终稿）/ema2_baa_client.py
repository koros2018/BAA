#!/usr/bin/env python3
"""
EMA2 × BAA API 客户端
----------------------
EMA2 项目通过此客户端调用 BAA 的图纸解析、合规审查和 BIM 重构服务。

使用方式：
    from baa_client import BAAClient
    client = BAAClient()
    
    # 健康检查
    status = client.health()
    
    # 免费审查
    result = client.review("drawing.dxf", building_type="civil")
    
    # 付费重构
    result = client.reconstruct("baa-file-xxx", "eyJhbG...", "order-001")

环境变量：
    BAA_API_URL       BAA服务地址，默认 http://localhost:8000
    BAA_API_KEY       API密钥
    BAA_TIMEOUT       超时秒数（默认60）
"""
import os
import time
import json
import logging
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger("ema2.baa_client")


class BAAClientError(Exception):
    """BAA客户端异常基类"""


class BAAClientAuthError(BAAClientError):
    """认证/授权相关异常"""


class BAAClientFileError(BAAClientError):
    """文件相关异常"""


class BAAClientServerError(BAAClientError):
    """服务端异常"""


# ── 异常映射：BAA error_code → Python异常类 ───────────────
ERROR_MAP = {
    "UNSUPPORTED_FORMAT": BAAClientFileError,
    "FILE_TOO_LARGE": BAAClientFileError,
    "PARSE_FAILED": BAAClientServerError,
    "ENGINE_ERROR": BAAClientServerError,
    "AUTH_FAILED": BAAClientAuthError,
    "TOKEN_EXPIRED": BAAClientAuthError,
    "FILE_NOT_FOUND": BAAClientFileError,
    "RECONSTRUCT_FAILED": BAAClientServerError,
}

# ── 用户可见的错误提示 ──────────────────────────────────────
USER_MESSAGES = {
    "UNSUPPORTED_FORMAT": "仅支持DXF/DWG格式",
    "FILE_TOO_LARGE": "文件超过50MB限制",
    "PARSE_FAILED": "图纸解析失败，请检查文件完整性",
    "ENGINE_ERROR": "系统处理异常，请重试",
    "AUTH_FAILED": "授权验证失败，请重新支付",
    "TOKEN_EXPIRED": "支付授权已过期，请重新支付",
    "FILE_NOT_FOUND": "文件已过期，请重新上传",
    "RECONSTRUCT_FAILED": "模型生成失败，请重试",
}


class BAAClient:
    """BAA API 客户端"""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: int = 3,
    ):
        self.api_url = (api_url or os.getenv("BAA_API_URL", "http://localhost:8000")).rstrip("/")
        self.api_key = api_key or os.getenv("BAA_API_KEY", "")
        self.timeout = timeout or int(os.getenv("BAA_TIMEOUT", "60"))
        self.max_retries = max_retries

    def _headers(self) -> Dict[str, str]:
        """构建请求头"""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _raise_on_error(self, result: dict, context: str = ""):
        """根据BAA返回的error_code抛出对应的Python异常"""
        if result.get("status") == "error":
            error_code = result.get("error_code", "UNKNOWN")
            message = result.get("message", f"BAA返回错误: {error_code}")
            exc_class = ERROR_MAP.get(error_code, BAAClientError)
            raise exc_class(f"[{error_code}] {message} (context: {context})")

    def get_user_message(self, result: dict) -> str:
        """将BAA的错误码转换为用户可见的提示文字"""
        error_code = result.get("error_code", "")
        return USER_MESSAGES.get(error_code, "系统异常，请稍后重试")

    # ── 健康检查 ──────────────────────────────────────────

    def health(self) -> dict:
        """检查BAA服务状态"""
        r = requests.get(
            f"{self.api_url}/health",
            headers=self._headers(),
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    # ── 免费服务 ──────────────────────────────────────────

    def deconstruct(self, file_path: str, building_type: str = "civil") -> dict:
        """图纸解构（免费）

        Args:
            file_path: 图纸文件路径（dxf/dwg）
            building_type: 建筑类型，civil(民用) / industrial(工业)

        Returns:
            解构结果，包含 elements 和 file_id

        Raises:
            BAAClientFileError: 文件不存在/格式不支持/过大
            BAAClientServerError: 解析失败/引擎错误
        """
        if not os.path.exists(file_path):
            raise BAAClientFileError(f"文件不存在: {file_path}")

        with open(file_path, "rb") as f:
            r = requests.post(
                f"{self.api_url}/deconstruct",
                files={"file": (os.path.basename(file_path), f)},
                params={"building_type": building_type},
                headers=self._headers(),
                timeout=self.timeout,
            )

        try:
            result = r.json()
        except Exception:
            raise BAAClientServerError(f"BAA返回非JSON响应: {r.status_code} {r.text[:200]}")

        self._raise_on_error(result, context=f"deconstruct({os.path.basename(file_path)})")
        return result

    def review(self, file_path: str, building_type: str = "civil",
               full: bool = False) -> dict:
        """图纸合规审查（免费）

        Args:
            file_path: 图纸文件路径（dxf/dwg）
            building_type: 建筑类型
            full: 是否返回完整图元列表

        Returns:
            审查结果，包含 summary 和 findings

        Raises:
            BAAClientFileError: 文件相关问题
            BAAClientServerError: 引擎问题
        """
        if not os.path.exists(file_path):
            raise BAAClientFileError(f"文件不存在: {file_path}")

        with open(file_path, "rb") as f:
            r = requests.post(
                f"{self.api_url}/review",
                files={"file": (os.path.basename(file_path), f)},
                params={"building_type": building_type, "full": str(full).lower()},
                headers=self._headers(),
                timeout=self.timeout,
            )

        try:
            result = r.json()
        except Exception:
            raise BAAClientServerError(f"BAA返回非JSON响应: {r.status_code} {r.text[:200]}")

        self._raise_on_error(result, context=f"review({os.path.basename(file_path)})")
        return result

    # ── 付费服务 ──────────────────────────────────────────

    def reconstruct(
        self,
        file_id: str,
        auth_token: str,
        order_id: str,
        options: Optional[dict] = None,
        retry_on_timeout: bool = True,
    ) -> dict:
        """BIM 重构（需auth_token）

        Args:
            file_id: 解构接口返回的 file_id
            auth_token: 授权代收代付点生成的支付授权令牌
            order_id: EMA2侧订单ID
            options: 重构参数（可选），如 {"lod": 200, "format": "ifc"}
            retry_on_timeout: 超时时是否重试一次

        Returns:
            重构结果，包含 model_file 和 auth_info

        Raises:
            BAAClientAuthError: auth_token无效/过期
            BAAClientFileError: file_id不存在
            BAAClientServerError: 重构失败
        """
        body = {
            "file_id": file_id,
            "auth_token": auth_token,
            "order_id": order_id,
        }
        if options:
            body["options"] = options

        reconstruct_timeout = int(os.getenv("BAA_RECONSTRUCT_TIMEOUT", "120"))

        for attempt in range(2 if retry_on_timeout else 1):
            try:
                r = requests.post(
                    f"{self.api_url}/reconstruct",
                    json=body,
                    headers=self._headers(),
                    timeout=reconstruct_timeout,
                )
            except requests.Timeout:
                if attempt == 0 and retry_on_timeout:
                    logger.warning("reconstruct超时，第1次重试")
                    continue
                raise BAAClientServerError("BAA重构服务超时，请稍后重试")

            break

        try:
            result = r.json()
        except Exception:
            raise BAAClientServerError(f"BAA返回非JSON响应: {r.status_code} {r.text[:200]}")

        self._raise_on_error(result, context=f"reconstruct(file_id={file_id})")
        return result

    # ── 状态查询 ──────────────────────────────────────────

    def check_order(self, order_id: str) -> dict:
        """查询任务状态

        Args:
            order_id: BAA侧的order_id

        Returns:
            order状态: {order_id, status, created_at, result}
        """
        r = requests.get(
            f"{self.api_url}/order/{order_id}",
            headers=self._headers(),
            timeout=10,
        )

        try:
            result = r.json()
        except Exception:
            raise BAAClientServerError(f"BAA返回非JSON响应: {r.status_code} {r.text[:200]}")

        self._raise_on_error(result, context=f"check_order({order_id})")
        return result

    # ── 任务编排（完整流程） ──────────────────────────────

    def run_full_flow(self, file_path: str, building_type: str = "civil",
                      auth_token: str = None, order_id: str = None,
                      reconstruct_options: dict = None) -> dict:
        """完整任务流程：审查 → (可选)重构

        Args:
            file_path: 图纸文件路径
            building_type: 建筑类型
            auth_token: 授权令牌（如果为None，仅执行审查）
            order_id: 订单ID（如果为None，自动生成）
            reconstruct_options: 重构参数

        Returns:
            {
                "phase": "review_completed" | "reconstruct_completed" | "error",
                "review_result": {...},    # 审查结果
                "reconstruct_result": {...} # 重构结果（可选）
                "error": {...}             # 错误信息（可选）
            }
        """
        result = {"phase": "", "review_result": None}

        try:
            # Step 1: 审查
            review_result = self.review(file_path, building_type=building_type)
            result["review_result"] = review_result
            result["phase"] = "review_completed"

            if review_result.get("status") != "success":
                result["phase"] = "error"
                result["error"] = review_result
                return result

            # 如果没有auth_token，停止在审查阶段
            if not auth_token:
                return result

            file_id = review_result["file_id"]
            oid = order_id or f"ema2-order-{int(time.time())}"

            # Step 2: 重构
            reconstruct_result = self.reconstruct(
                file_id=file_id,
                auth_token=auth_token, 
                order_id=oid,
                options=reconstruct_options,
            )
            result["reconstruct_result"] = reconstruct_result
            result["phase"] = "reconstruct_completed"

        except BAAClientAuthError as e:
            result["phase"] = "error"
            result["error"] = {
                "error_code": "AUTH_FAILED",
                "message": str(e),
                "user_message": "授权验证失败，请重新支付",
            }
        except (BAAClientFileError, BAAClientServerError) as e:
            result["phase"] = "error"
            result["error"] = {
                "error_code": type(e).__name__,
                "message": str(e),
                "user_message": self.get_user_message({"error_code": "ENGINE_ERROR"}),
            }
        except Exception as e:
            result["phase"] = "error"
            result["error"] = {
                "error_code": "SYSTEM_ERROR",
                "message": str(e),
                "user_message": "系统异常，请稍后重试",
            }

        return result


# ── 便捷函数 ────────────────────────────────────────────────

def get_client() -> BAAClient:
    """获取默认配置的BAAClient（从环境变量读取配置）"""
    return BAAClient()


# ── 命令行使用 ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法:")
        print("  python baa_client.py health")
        print("  python baa_client.py review <file.dxf> [building_type]")
        print("  python baa_client.py deconstruct <file.dxf> [building_type]")
        print("  python baa_client.py reconstruct <file_id> <auth_token> <order_id> [options_json]")
        print("  python baa_client.py order <order_id>")
        sys.exit(1)

    client = get_client()
    cmd = sys.argv[1]

    try:
        if cmd == "health":
            result = client.health()
        elif cmd == "deconstruct":
            fp = sys.argv[2]
            bt = sys.argv[3] if len(sys.argv) > 3 else "civil"
            result = client.deconstruct(fp, building_type=bt)
        elif cmd == "review":
            fp = sys.argv[2]
            bt = sys.argv[3] if len(sys.argv) > 3 else "civil"
            result = client.review(fp, building_type=bt)
        elif cmd == "reconstruct":
            fid = sys.argv[2]
            token = sys.argv[3]
            oid = sys.argv[4]
            opts = json.loads(sys.argv[5]) if len(sys.argv) > 5 else None
            result = client.reconstruct(fid, token, oid, options=opts)
        elif cmd == "order":
            result = client.check_order(sys.argv[2])
        else:
            print(f"未知命令: {cmd}")
            sys.exit(1)

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except BAAClientError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
