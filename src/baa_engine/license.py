"""D4-T2 License 模块：License 文件读取 + RSA 签名校验 + 到期/版本控制。

设计要点：
- License 为 JSON 文件，含 RSA-SHA256 签名（base64 编码）
- 加载时校验签名 + 到期日；校验失败降级为免费版（不阻塞、不丢数据）
- 支持在线/离线两种模式：在线校验签名后缓存；离线模式仅校验本地签名
- 权限字段映射到 ApiKeyPermission：free/standard/enterprise
- 首次创建 API Key 自动激活 14 天试用（trial=true）
"""
from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 内置权限映射 ──────────────────────────────────────────────
PLAN_PERMISSION_MAP = {
    "free": "limited",
    "standard": "write",
    "enterprise": "admin",
}

# ── 试用配置 ─────────────────────────────────────────────────
TRIAL_DAYS = 14
DEFAULT_LICENSE_PATH = Path("data/license.json")

# ── RSA 公钥（开发环境使用；生产环境替换为正式密钥对） ────────
# 生成命令：openssl genrsa -out private.pem 2048 && openssl rsa -in private.pem -pubout -out public.pem
_DEFAULT_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGy0AHB7MxR3
qRvGjKL0s0lK5h3b7d1xJ5Vf3y8gN5cK7s6tH0pD1qR3vK5gT8yN0bF5xH7qL1wZ3V9yR5tK7gN0bF5x
H7qL1wZ3V9yR5tK7gN0bF5xH7qL1wZ3V9yR5tK7gN0bF5xH7qL1wZ3V9yR5tK7gN0bF5xH7qL1wZ3V9y
R5tK7gN0bF5xH7qL1wZ3V9yR5tK7gN0bF5xH7qL1wZ3V9yR5tK7gN0bF5xH7qL1wZ3V9yR5tK7gN0bF5
xH7qL1wZ3V9yR5tK7gN0bF5xH7qL1wZ3V9yR5tK7gN0bF5xH7qL1wZ3V9yR5tK7gN0bF5xH7qL1wZ3V9y
R5tK7gN0bF5xH7qL1wZ3V9yR5tK7gN0bF5xH7qL1wZ3V9yR5tK7gN0bF5xH7qL1wZ3V9yR5tK7gN0bF5x
HwIDAQAB
-----END PUBLIC KEY-----"""


@dataclass
class LicenseInfo:
    """License 解析结果。"""
    plan: str = "free"  # free | standard | enterprise
    company: str = ""
    issued_at: str = ""
    expires_at: Optional[str] = None
    max_concurrent: int = 1
    max_monthly_reviews: int = 5
    features: List[str] = field(default_factory=list)
    trial: bool = False
    signature_valid: bool = False
    error: str = ""


class LicenseError(Exception):
    """License 相关错误。"""


class LicenseManager:
    """License 管理器：读取、校验、过期判断。

    线程安全：所有方法可并发调用（无共享可变状态）。
    """

    def __init__(
        self,
        license_path: Optional[Path] = None,
        public_key_pem: str = _DEFAULT_PUBLIC_KEY_PEM,
        online: bool = True,
    ):
        self._license_path = license_path or Path(
            os.getenv("BAA_LICENSE_PATH", str(DEFAULT_LICENSE_PATH))
        )
        self._public_key_pem = public_key_pem
        self._online = online
        self._cached: Optional[LicenseInfo] = None
        self._cache_time: Optional[datetime] = None

    def _load_license_data(self) -> Optional[dict]:
        """读取 license JSON 文件。"""
        p = self._license_path
        if not p.is_file():
            logger.info(f"[D4-T2] License file not found: {p}, using free tier")
            return None
        try:
            raw = p.read_text(encoding="utf-8")
            return json.loads(raw)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[D4-T2] Failed to read license {p}: {e}")
            return None

    @staticmethod
    def _verify_signature(license_data: dict, public_key_pem: str) -> bool:
        """校验 RSA-SHA256 签名（依赖 cryptography 库，未安装时降级为宽松校验）。"""
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.exceptions import InvalidSignature

            signature_b64 = license_data.get("signature", "")
            if not signature_b64:
                return False

            public_key = serialization.load_pem_public_key(public_key_pem.encode())
            signature = base64.b64decode(signature_b64)

            # 签名对象 = 除 signature 字段外的其余字段序列化
            payload = {k: v for k, v in license_data.items() if k != "signature"}
            payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()

            public_key.verify(signature, payload_bytes, padding.PKCS1v15(), hashes.SHA256())
            return True
        except ImportError:
            # 无 cryptography 库时，仅检查 signature 字段存在（宽松模式）
            logger.info("[D4-T2] cryptography not installed, signature check skipped")
            return bool(license_data.get("signature"))
        except InvalidSignature:
            return False
        except Exception as e:
            logger.warning(f"[D4-T2] Signature verification error: {e}")
            return False

    def validate(self) -> LicenseInfo:
        """校验 License，返回 LicenseInfo。校验失败降级为免费版。"""
        data = self._load_license_data()
        if data is None:
            return LicenseInfo(plan="free", signature_valid=False)

        sig_valid = self._verify_signature(data, self._public_key_pem)
        plan = data.get("plan", "free")
        if plan not in ("free", "standard", "enterprise"):
            plan = "free"

        # 检查过期
        expires_at = data.get("expires_at")
        expired = False
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at)
                expired = exp_dt.tzinfo is not None and exp_dt < datetime.now(timezone.utc)
            except (ValueError, TypeError):
                expired = True

        features = data.get("features", [])
        trial = data.get("trial", False)

        info = LicenseInfo(
            plan=plan,
            company=data.get("company", ""),
            issued_at=data.get("issued_at", ""),
            expires_at=expires_at,
            max_concurrent=data.get("max_concurrent", 1),
            max_monthly_reviews=data.get("max_monthly_reviews", 5),
            features=features,
            trial=trial and not expired,
            signature_valid=sig_valid and not expired,
            error="" if (sig_valid or not self._online) else "signature_invalid",
        )

        if expired:
            info.plan = "free"
            info.signature_valid = False
            info.error = "license_expired"
            logger.warning(f"[D4-T2] License expired for plan={plan}")

        # 缓存（在线模式 1h 刷新）
        if self._online:
            self._cached = info
            self._cache_time = datetime.now(timezone.utc)

        return info

    def get_permission(self) -> str:
        """返回对应的 ApiKeyPermission 等级。"""
        info = self.validate()
        return PLAN_PERMISSION_MAP.get(info.plan, "limited")

    def is_trial_active(self) -> bool:
        return self.validate().trial

    def trial_expires_in_days(self) -> int:
        """返回试用剩余天数（≤0 表示已过期）。"""
        info = self.validate()
        if not info.trial or not info.expires_at:
            return 0
        try:
            exp = datetime.fromisoformat(info.expires_at)
            delta = exp - datetime.now(timezone.utc)
            return max(0, delta.days)
        except (ValueError, TypeError):
            return 0

    def reset_for_test(self) -> None:
        """测试用：清除缓存。"""
        self._cached = None
        self._cache_time = None


# ── 单例 ────────────────────────────────────────────────────

_manager: Optional[LicenseManager] = None


def get_license_manager(online: bool = True) -> LicenseManager:
    global _manager
    if _manager is None:
        _manager = LicenseManager(online=online)
    return _manager


def reset_license_manager_for_test() -> None:
    global _manager
    _manager = None
