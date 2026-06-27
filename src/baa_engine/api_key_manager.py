"""
BAA API密钥管理器
==================
提供 API Key 的生成、存储、验证、过期管理、权限分级、用量统计。

设计目标：
- 自动生成安全密钥（secrets.token_urlsafe）
- 多密钥并行有效（轮换宽限期）
- 密钥过期机制（可配置TTL）
- 权限分级：admin / read / write / limited
- 用量统计：调用次数、最后使用时间
- 持久化：JSON文件存储，加密存储密钥hash
"""

import secrets
import hashlib
import hmac
import json
import time
import os
import base64
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List, Set


# ── AES-GCM 加密（密钥可恢复，用于前端展示） ──────────────

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


# 用于加密 raw_key 的主密钥（从环境变量派生，或自动生成一个持久化的）
_ENCRYPTION_MASTER_KEY = None
_ENCRYPTION_KEY_LOCK = threading.Lock()


def _get_encryption_key() -> bytes:
    """获取/初始化 AES-256 主密钥（32 bytes）
    
    优先级：
    1. 环境变量 BAA_KEY_ENCRYPTION_KEY（32字节 hex）
    2. 持久化存储的密钥文件 data/.key_encryption.key
    3. 自动生成并保存
    """
    global _ENCRYPTION_MASTER_KEY
    if _ENCRYPTION_MASTER_KEY is not None:
        return _ENCRYPTION_MASTER_KEY
    
    with _ENCRYPTION_KEY_LOCK:
        if _ENCRYPTION_MASTER_KEY is not None:
            return _ENCRYPTION_MASTER_KEY
        
        # 1. 环境变量
        env_key = os.getenv("BAA_KEY_ENCRYPTION_KEY", "")
        if env_key:
            try:
                _ENCRYPTION_MASTER_KEY = bytes.fromhex(env_key)
                if len(_ENCRYPTION_MASTER_KEY) == 32:
                    return _ENCRYPTION_MASTER_KEY
            except ValueError:
                pass
        
        # 2. 持久化密钥文件
        storage_dir = Path(__file__).resolve().parent.parent.parent / "data"
        key_file = storage_dir / ".key_encryption.key"
        if key_file.exists():
            raw = key_file.read_bytes().strip()
            if len(raw) == 32:
                _ENCRYPTION_MASTER_KEY = raw
                return _ENCRYPTION_MASTER_KEY
        
        # 3. 自动生成
        storage_dir.mkdir(parents=True, exist_ok=True)
        new_key = AESGCM.generate_key(bit_length=256)
        key_file.write_bytes(new_key)
        os.chmod(str(key_file), 0o600)  # 仅 owner 可读写
        _ENCRYPTION_MASTER_KEY = new_key
        return _ENCRYPTION_MASTER_KEY


def encrypt_raw_key(raw_key: str) -> str:
    """AES-GCM 加密 raw_key，返回 base64 编码密文"""
    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # GCM 推荐 96-bit nonce
    ciphertext = aesgcm.encrypt(nonce, raw_key.encode("utf-8"), None)
    # 格式: base64(nonce + ciphertext)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_raw_key(encrypted: str) -> Optional[str]:
    """解密 raw_key，失败返回 None"""
    try:
        key = _get_encryption_key()
        data = base64.b64decode(encrypted)
        nonce = data[:12]
        ciphertext = data[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except Exception:
        return None


# ── 权限等级 ──────────────────────────────────────────────

class ApiKeyPermission:
    ADMIN = "admin"       # 完全控制（创建/撤销密钥、管理）
    WRITE = "write"       # 可上传图纸、发起审查
    READ = "read"         # 可查询订单/结果
    LIMITED = "limited"   # 只读+限制调用频率

    ALL = (ADMIN, WRITE, READ, LIMITED)

    @classmethod
    def validate(cls, perm: str) -> bool:
        return perm in cls.ALL


# ── 默认配置 ──────────────────────────────────────────────

DEFAULT_KEY_TTL_DAYS = 90          # 密钥默认有效期90天
DEFAULT_RATE_LIMIT = {             # 每密钥每分钟限制
    "admin": 1000,
    "write": 100,
    "read": 60,
    "limited": 10,
}
DEFAULT_STORAGE_PATH = "data/api_keys.json"


# ── 密钥管理器 ──────────────────────────────────────────────

class ApiKeyManager:
    """API 密钥全生命周期管理"""

    def __init__(self, storage_path: str = None, env_key: str = None):
        self._lock = threading.Lock()
        self._storage_path = storage_path or os.getenv(
            "BAA_API_KEYS_PATH",
            str(Path(__file__).resolve().parent.parent.parent / DEFAULT_STORAGE_PATH)
        )
        self._keys: Dict[str, dict] = {}  # key_id → key_info
        self._usage: Dict[str, dict] = {}  # key_id → {calls, last_used, per_minute}
        self._env_key = env_key or os.getenv("BAA_API_KEY", "")
        self._loaded = False

    # ── 持久化 ──────────────────────────────────────────

    def _ensure_storage_dir(self):
        Path(self._storage_path).parent.mkdir(parents=True, exist_ok=True)

    def _hash_key(self, raw_key: str) -> str:
        """对API Key做单向哈希存储"""
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def _verify_key(self, raw_key: str, stored_hash: str) -> bool:
        return hmac.compare_digest(self._hash_key(raw_key), stored_hash)

    def load(self):
        """从持久化存储加载密钥"""
        if self._loaded:
            return
        self._reload()

    def _reload(self):
        """强制从文件重新加载（跳过 _loaded 短路）"""
        self._ensure_storage_dir()
        if os.path.exists(self._storage_path):
            try:
                with open(self._storage_path) as f:
                    data = json.load(f)
                with self._lock:
                    self._keys = data.get("keys", {})
                    self._usage = data.get("usage", {})
            except (json.JSONDecodeError, IOError):
                pass
        self._loaded = True

    def save(self):
        """持久化存储到文件"""
        self._ensure_storage_dir()
        with self._lock:
            data = {
                "keys": self._keys,
                "usage": self._usage,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        # 原子写入：先写临时文件再rename
        tmp = self._storage_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._storage_path)

    # ── 密钥生成 ──────────────────────────────────────────

    def generate_key(
        self,
        permission: str = "write",
        ttl_days: int = None,
        label: str = "",
        created_by: str = "system",
    ) -> dict:
        """生成新 API Key

        Args:
            permission: 权限等级
            ttl_days: 有效期天数（默认90天）
            label: 用途标签（如"生产-前端"、"测试-张三"）
            created_by: 创建者标识

        Returns:
            {"key_id": str, "raw_key": str, "info": dict}
        """
        self.load()
        if not ApiKeyPermission.validate(permission):
            raise ValueError(f"无效权限等级: {permission}")

        ttl = ttl_days or DEFAULT_KEY_TTL_DAYS
        raw_key = f"baa_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_key(raw_key)
        key_id = f"key_{secrets.token_hex(8)}"

        now = datetime.now(timezone.utc)
        expires_at = now.timestamp() + ttl * 86400

        # AES-GCM 加密存储 raw_key（前端可恢复查看/复制）
        encrypted_raw = encrypt_raw_key(raw_key)

        key_info = {
            "key_id": key_id,
            "hash": key_hash,
            "encrypted_raw": encrypted_raw,  # AES-GCM 密文，可解密为原始密钥
            "permission": permission,
            "label": label,
            "created_by": created_by,
            "created_at": now.isoformat(),
            "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
            "ttl_days": ttl,
            "enabled": True,
            "last_used": None,
            "calls": 0,
        }

        with self._lock:
            self._keys[key_id] = key_info
            self._usage[key_id] = {"calls": 0, "last_used": None, "per_minute": []}

        self.save()

        # 返回时不包含hash和encrypted_raw
        return_info = {k: v for k, v in key_info.items() if k not in ("hash", "encrypted_raw")}
        return {
            "key_id": key_id,
            "raw_key": raw_key,   # 创建时返回，后续可通过 decrypt 恢复
            "info": return_info,
        }

    def generate_admin_key(self) -> dict:
        """生成初始admin密钥（从环境变量加载时调用）"""
        return self.generate_key(
            permission="admin",
            ttl_days=365,
            label="admin-initial",
            created_by="system"
        )

    # ── 密钥验证 ──────────────────────────────────────────

    def validate_key(self, raw_key: str) -> Optional[dict]:
        """验证API Key，返回key_info（无hash）或None"""
        self.load()

        # 先检查环境变量密钥（管理员通道）
        if self._env_key and hmac.compare_digest(raw_key, self._env_key):
            return {
                "key_id": "__env__",
                "permission": "admin",
                "label": "env-key",
                "enabled": True,
                "expires_at": None,
            }

        for key_id, info in self._keys.items():
            if not info.get("enabled", True):
                continue
            if self._verify_key(raw_key, info["hash"]):
                # 检查过期
                expires = info.get("expires_at")
                if expires:
                    exp_time = datetime.fromisoformat(expires)
                    if exp_time.tzinfo is None:
                        exp_time = exp_time.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) > exp_time:
                        continue  # 已过期
                return {k: v for k, v in info.items() if k != "hash"}
        return None

    # ── 密钥管理 ──────────────────────────────────────────

    def list_keys(self, include_disabled: bool = False, include_raw: bool = False) -> List[dict]:
        """列出所有密钥

        Args:
            include_disabled: 是否包含已禁用的
            include_raw: 是否解密并返回 raw_key（前端密钥详情页使用）
        """
        self.load()
        result = []
        for key_id, info in self._keys.items():
            if not include_disabled and not info.get("enabled", True):
                continue
            entry = {k: v for k, v in info.items() if k != "hash"}
            # 合并用量
            usage = self._usage.get(key_id, {})
            entry["calls"] = usage.get("calls", 0)
            entry["last_used"] = usage.get("last_used")
            # 解密 raw_key（前端可用）
            encrypted = info.get("encrypted_raw", "")
            if include_raw and encrypted:
                raw = decrypt_raw_key(encrypted)
                entry["raw_key"] = raw if raw else None
                entry["has_raw_key"] = raw is not None
            else:
                entry["has_raw_key"] = bool(encrypted)
            result.append(entry)
        return sorted(result, key=lambda x: x.get("created_at", ""), reverse=True)

    def revoke_key(self, key_id: str) -> bool:
        """撤销密钥"""
        self._reload()
        with self._lock:
            if key_id not in self._keys:
                return False
            self._keys[key_id]["enabled"] = False
        self.save()
        return True

    def rotate_key(self, key_id: str, new_ttl_days: int = None) -> Optional[dict]:
        """轮换密钥：保留key_id和权限，生成新密钥值

        旧密钥立即失效，新密钥开始使用。
        建议：先创建新密钥（generate_key），旧密钥宽限期再撤销。
        """
        self.load()
        with self._lock:
            if key_id not in self._keys:
                return None
            old_info = self._keys[key_id]
            if not old_info.get("enabled", True):
                return None

            # 生成新密钥值
            raw_key = f"baa_{secrets.token_urlsafe(32)}"
            new_hash = self._hash_key(raw_key)

            now = datetime.now(timezone.utc)
            ttl = new_ttl_days or old_info.get("ttl_days", DEFAULT_KEY_TTL_DAYS)
            expires_at = now.timestamp() + ttl * 86400

            encrypted_raw = encrypt_raw_key(raw_key)
            self._keys[key_id]["hash"] = new_hash
            self._keys[key_id]["encrypted_raw"] = encrypted_raw
            self._keys[key_id]["ttl_days"] = ttl
            self._keys[key_id]["expires_at"] = datetime.fromtimestamp(
                expires_at, tz=timezone.utc
            ).isoformat()
            self._keys[key_id]["created_at"] = now.isoformat()

        self.save()
        return {
            "key_id": key_id,
            "raw_key": raw_key,
            "info": {k: v for k, v in self._keys[key_id].items() if k not in ("hash", "encrypted_raw")},
        }

    def delete_key(self, key_id: str) -> bool:
        """删除密钥（不可恢复）"""
        self._reload()
        with self._lock:
            if key_id not in self._keys:
                return False
            del self._keys[key_id]
            self._usage.pop(key_id, None)
        self.save()
        return True

    # ── 用量统计 ──────────────────────────────────────────

    def record_usage(self, raw_key: str):
        """记录API调用"""
        self.load()
        # 环境变量key不记录
        if self._env_key and hmac.compare_digest(raw_key, self._env_key):
            return

        key_id = None
        for kid, info in self._keys.items():
            if self._verify_key(raw_key, info["hash"]):
                key_id = kid
                break

        if not key_id:
            return

        now = time.time()
        with self._lock:
            usage = self._usage.setdefault(key_id, {"calls": 0, "last_used": None, "per_minute": []})
            usage["calls"] += 1
            usage["last_used"] = datetime.now(timezone.utc).isoformat()
            # 每分钟计数（保留最近5分钟）
            minute_bucket = int(now // 60)
            usage["per_minute"] = [b for b in usage.get("per_minute", [])
                                   if b[0] > minute_bucket - 5]
            usage["per_minute"].append((minute_bucket, now))

    def get_usage_stats(self, key_id: str = None) -> dict:
        """获取用量统计"""
        self.load()
        if key_id:
            usage = self._usage.get(key_id, {})
            key_info = self._keys.get(key_id, {})
            if not key_info:
                return {}
            return {
                "key_id": key_id,
                "label": key_info.get("label", ""),
                "permission": key_info.get("permission", ""),
                "total_calls": usage.get("calls", 0),
                "last_used": usage.get("last_used"),
                "created_at": key_info.get("created_at"),
                "expires_at": key_info.get("expires_at"),
                "enabled": key_info.get("enabled", True),
            }

        stats = {}
        for kid in self._keys:
            stats[kid] = self.get_usage_stats(kid)
        return stats

    def check_rate_limit(self, raw_key: str) -> bool:
        """检查是否超限（返回False表示超出限制）"""
        self.load()
        # 环境变量key不限制
        if self._env_key and hmac.compare_digest(raw_key, self._env_key):
            return True

        key_info = self.validate_key(raw_key)
        if not key_info:
            return False

        key_id = key_info["key_id"]
        perm = key_info.get("permission", "limited")
        limit = DEFAULT_RATE_LIMIT.get(perm, 10)

        now = time.time()
        minute_bucket = int(now // 60)

        with self._lock:
            usage = self._usage.setdefault(key_id, {"calls": 0, "last_used": None, "per_minute": []})
            # 清理旧bucket
            usage["per_minute"] = [b for b in usage.get("per_minute", [])
                                   if b[0] == minute_bucket]
            return len(usage["per_minute"]) < limit

    # ── 清理过期密钥 ──────────────────────────────────────────

    def cleanup_expired(self) -> int:
        """清理过期密钥（标记为disabled），返回清理数"""
        self.load()
        now = datetime.now(timezone.utc)
        cleaned = 0
        with self._lock:
            for key_id, info in list(self._keys.items()):
                expires = info.get("expires_at")
                if expires:
                    exp_time = datetime.fromisoformat(expires)
                    if exp_time.tzinfo is None:
                        exp_time = exp_time.replace(tzinfo=timezone.utc)
                    if now > exp_time:
                        self._keys[key_id]["enabled"] = False
                        cleaned += 1
        if cleaned:
            self.save()
        return cleaned

    # ── 从环境变量初始化 ──────────────────────────────────

    def ensure_env_key_exists(self):
        """确保环境变量中的API Key已在管理器中注册"""
        if not self._env_key:
            return None
        self.load()

        # 检查是否已存在
        for info in self._keys.values():
            if info.get("label") == "env-key":
                return info.get("key_id")

        # 注册
        raw_key = self._env_key
        key_hash = self._hash_key(raw_key)
        key_id = "key_env_admin"

        key_info = {
            "key_id": key_id,
            "hash": key_hash,
            "encrypted_raw": encrypt_raw_key(raw_key),
            "permission": "admin",
            "label": "env-key",
            "created_by": "env",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": None,
            "ttl_days": None,
            "enabled": True,
            "last_used": None,
            "calls": 0,
        }
        with self._lock:
            self._keys[key_id] = key_info
            self._usage[key_id] = {"calls": 0, "last_used": None, "per_minute": []}
        self.save()
        return key_id


# ── 全局单例 ──────────────────────────────────────────────

_key_manager = None


def get_key_manager() -> ApiKeyManager:
    global _key_manager
    if _key_manager is None:
        _key_manager = ApiKeyManager()
        _key_manager.load()
        _key_manager.ensure_env_key_exists()
        _key_manager.cleanup_expired()
    return _key_manager