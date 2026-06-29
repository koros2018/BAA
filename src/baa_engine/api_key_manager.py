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
_ENCRYPTION_MASTER_KEY = None  # 赋值
_ENCRYPTION_KEY_LOCK = threading.Lock()  # 赋值


def _get_encryption_key() -> bytes:
    """获取/初始化 AES-256 主密钥（32 bytes）
    
    优先级：
    1. 环境变量 BAA_KEY_ENCRYPTION_KEY（32字节 hex）
    2. 持久化存储的密钥文件 data/.key_encryption.key
    3. 自动生成并保存
    """
    global _ENCRYPTION_MASTER_KEY  # 全局变量
    if _ENCRYPTION_MASTER_KEY is not None:  # 条件判断
        return _ENCRYPTION_MASTER_KEY  # 返回
    
    with _ENCRYPTION_KEY_LOCK:  # 上下文管理
        if _ENCRYPTION_MASTER_KEY is not None:  # 条件判断
            return _ENCRYPTION_MASTER_KEY  # 返回
        
        # 1. 环境变量
        env_key = os.getenv("BAA_KEY_ENCRYPTION_KEY", "")  # 赋值
        if env_key:  # 条件判断
            try:  # 尝试
                _ENCRYPTION_MASTER_KEY = bytes.fromhex(env_key)  # 赋值
                if len(_ENCRYPTION_MASTER_KEY) == 32:  # 条件判断
                    return _ENCRYPTION_MASTER_KEY  # 返回
            except ValueError:  # 捕获异常
                pass  # 占位
        
        # 2. 持久化密钥文件
        storage_dir = Path(__file__).resolve().parent.parent.parent / "data"  # 赋值
        key_file = storage_dir / ".key_encryption.key"  # 赋值
        if key_file.exists():  # 条件判断
            raw = key_file.read_bytes().strip()  # 赋值
            if len(raw) == 32:  # 条件判断
                _ENCRYPTION_MASTER_KEY = raw  # 赋值
                return _ENCRYPTION_MASTER_KEY  # 返回
        
        # 3. 自动生成
        storage_dir.mkdir(parents=True, exist_ok=True)  # 调用
        new_key = AESGCM.generate_key(bit_length=256)  # 赋值
        key_file.write_bytes(new_key)  # 调用
        os.chmod(str(key_file), 0o600)  # 仅 owner 可读写
        _ENCRYPTION_MASTER_KEY = new_key  # 赋值
        return _ENCRYPTION_MASTER_KEY  # 返回


def encrypt_raw_key(raw_key: str) -> str:
    """AES-GCM 加密 raw_key，返回 base64 编码密文"""
    key = _get_encryption_key()  # 赋值
    aesgcm = AESGCM(key)  # 赋值
    nonce = os.urandom(12)  # GCM 推荐 96-bit nonce
    ciphertext = aesgcm.encrypt(nonce, raw_key.encode("utf-8"), None)  # 赋值
    # 格式: base64(nonce + ciphertext)
    return base64.b64encode(nonce + ciphertext).decode("ascii")  # 返回


def decrypt_raw_key(encrypted: str) -> Optional[str]:
    """解密 raw_key，失败返回 None"""
    try:  # 尝试
        key = _get_encryption_key()  # 赋值
        data = base64.b64decode(encrypted)  # 赋值
        nonce = data[:12]  # 赋值
        ciphertext = data[12:]  # 赋值
        aesgcm = AESGCM(key)  # 赋值
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)  # 赋值
        return plaintext.decode("utf-8")  # 返回
    except Exception:  # 捕获异常
        return None  # 返回


# ── 权限等级 ──────────────────────────────────────────────

class ApiKeyPermission:
    ADMIN = "admin"       # 完全控制（创建/撤销密钥、管理）
    WRITE = "write"       # 可上传图纸、发起审查
    READ = "read"         # 可查询订单/结果
    LIMITED = "limited"   # 只读+限制调用频率

    ALL = (ADMIN, WRITE, READ, LIMITED)  # 赋值

    @classmethod
    def validate(cls, perm: str) -> bool:
        return perm in cls.ALL  # 返回


# ── 默认配置 ──────────────────────────────────────────────

DEFAULT_KEY_TTL_DAYS = 90          # 密钥默认有效期90天
DEFAULT_RATE_LIMIT = {             # 每密钥每分钟限制
    "admin": 1000,
    "write": 100,
    "read": 60,
    "limited": 10,
}
DEFAULT_STORAGE_PATH = "data/api_keys.json"  # 赋值


# ── 密钥管理器 ──────────────────────────────────────────────

class ApiKeyManager:
    """API 密钥全生命周期管理"""

    def __init__(self, storage_path: str = None, env_key: str = None):
        self._lock = threading.Lock()  # 赋值
        self._storage_path = storage_path or os.getenv(  # 赋值
            "BAA_API_KEYS_PATH",
            str(Path(__file__).resolve().parent.parent.parent / DEFAULT_STORAGE_PATH)  # 调用
        )
        self._keys: Dict[str, dict] = {}  # key_id → key_info
        self._usage: Dict[str, dict] = {}  # key_id → {calls, last_used, per_minute}
        self._env_key = env_key or os.getenv("BAA_API_KEY", "")  # 赋值
        self._loaded = False  # 赋值

    # ── 持久化 ──────────────────────────────────────────

    def _ensure_storage_dir(self):
        Path(self._storage_path).parent.mkdir(parents=True, exist_ok=True)  # 调用

    def _hash_key(self, raw_key: str) -> str:
        """对API Key做单向哈希存储"""
        return hashlib.sha256(raw_key.encode()).hexdigest()  # 返回

    def _verify_key(self, raw_key: str, stored_hash: str) -> bool:
        return hmac.compare_digest(self._hash_key(raw_key), stored_hash)  # 返回

    def load(self):
        """从持久化存储加载密钥"""
        if self._loaded:  # 条件判断
            return  # 返回
        self._reload()  # 调用

    def _reload(self):
        """强制从文件重新加载（跳过 _loaded 短路）"""
        self._ensure_storage_dir()  # 调用
        if os.path.exists(self._storage_path):  # 条件判断
            try:  # 尝试
                with open(self._storage_path) as f:  # 上下文管理
                    data = json.load(f)  # 赋值
                with self._lock:  # 上下文管理
                    self._keys = data.get("keys", {})  # 赋值
                    self._usage = data.get("usage", {})  # 赋值
            except (json.JSONDecodeError, IOError):  # 捕获异常
                pass  # 占位
        self._loaded = True  # 赋值

    def save(self):
        """持久化存储到文件"""
        self._ensure_storage_dir()  # 调用
        with self._lock:  # 上下文管理
            data = {  # 赋值
                "keys": self._keys,
                "usage": self._usage,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        # 原子写入：先写临时文件再rename
        tmp = self._storage_path + ".tmp"  # 赋值
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)  # 调用
        os.replace(tmp, self._storage_path)  # 调用

    # ── 密钥生成 ──────────────────────────────────────────

    def generate_key(
        self,  # 解包
        permission: str = "write",  # 赋值
        ttl_days: int = None,  # 赋值
        label: str = "",  # 赋值
        created_by: str = "system",  # 赋值
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
        self.load()  # 调用
        if not ApiKeyPermission.validate(permission):  # 条件判断
            raise ValueError(f"无效权限等级: {permission}")

        ttl = ttl_days or DEFAULT_KEY_TTL_DAYS  # 赋值
        raw_key = f"baa_{secrets.token_urlsafe(32)}"  # 赋值
        key_hash = self._hash_key(raw_key)  # 赋值
        key_id = f"key_{secrets.token_hex(8)}"  # 赋值

        now = datetime.now(timezone.utc)  # 赋值
        expires_at = now.timestamp() + ttl * 86400  # 赋值

        # AES-GCM 加密存储 raw_key（前端可恢复查看/复制）
        encrypted_raw = encrypt_raw_key(raw_key)  # 赋值

        key_info = {  # 赋值
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

        with self._lock:  # 上下文管理
            self._keys[key_id] = key_info  # 赋值
            self._usage[key_id] = {"calls": 0, "last_used": None, "per_minute": []}

        self.save()  # 调用

        # 返回时不包含hash和encrypted_raw
        return_info = {k: v for k, v in key_info.items() if k not in ("hash", "encrypted_raw")}  # 赋值
        return {  # 返回
            "key_id": key_id,
            "raw_key": raw_key,   # 创建时返回，后续可通过 decrypt 恢复
            "info": return_info,
        }

    def generate_admin_key(self) -> dict:
        """生成初始admin密钥（从环境变量加载时调用）"""
        return self.generate_key(  # 返回
            permission="admin",  # 赋值
            ttl_days=365,  # 赋值
            label="admin-initial",  # 赋值
            created_by="system"  # 赋值
        )

    # ── 密钥验证 ──────────────────────────────────────────

    def validate_key(self, raw_key: str) -> Optional[dict]:
        """验证API Key，返回key_info（无hash）或None"""
        self.load()  # 调用

        # 先检查环境变量密钥（管理员通道）
        if self._env_key and hmac.compare_digest(raw_key, self._env_key):  # 条件判断
            return {  # 返回
                "key_id": "__env__",
                "permission": "admin",
                "label": "env-key",
                "enabled": True,
                "expires_at": None,
            }

        for key_id, info in self._keys.items():  # 循环
            if not info.get("enabled", True):  # 条件判断
                continue  # 继续循环
            if self._verify_key(raw_key, info["hash"]):  # 条件判断
                # 检查过期
                expires = info.get("expires_at")  # 赋值
                if expires:  # 条件判断
                    exp_time = datetime.fromisoformat(expires)  # 赋值
                    if exp_time.tzinfo is None:  # 条件判断
                        exp_time = exp_time.replace(tzinfo=timezone.utc)  # 赋值
                    if datetime.now(timezone.utc) > exp_time:  # 条件判断
                        continue  # 已过期
                return {k: v for k, v in info.items() if k != "hash"}  # 返回
        return None  # 返回

    # ── 密钥管理 ──────────────────────────────────────────

    def list_keys(self, include_disabled: bool = False, include_raw: bool = False) -> List[dict]:
        """列出所有密钥

        Args:
            include_disabled: 是否包含已禁用的
            include_raw: 是否解密并返回 raw_key（前端密钥详情页使用）
        """
        self.load()  # 调用
        result = []  # 赋值
        for key_id, info in self._keys.items():  # 循环
            if not include_disabled and not info.get("enabled", True):  # 条件判断
                continue  # 继续循环
            entry = {k: v for k, v in info.items() if k != "hash"}  # 赋值
            # 合并用量
            usage = self._usage.get(key_id, {})  # 赋值
            entry["calls"] = usage.get("calls", 0)
            entry["last_used"] = usage.get("last_used")
            # 解密 raw_key（前端可用）
            encrypted = info.get("encrypted_raw", "")  # 赋值
            if include_raw and encrypted:  # 条件判断
                raw = decrypt_raw_key(encrypted)  # 赋值
                entry["raw_key"] = raw if raw else None
                entry["has_raw_key"] = raw is not None
            else:  # 否则
                entry["has_raw_key"] = bool(encrypted)
            result.append(entry)  # 调用
        return sorted(result, key=lambda x: x.get("created_at", ""), reverse=True)  # 返回

    def revoke_key(self, key_id: str) -> bool:
        """撤销密钥"""
        self._reload()  # 调用
        with self._lock:  # 上下文管理
            if key_id not in self._keys:  # 条件判断
                return False  # 返回
            self._keys[key_id]["enabled"] = False
        self.save()  # 调用
        return True  # 返回

    def rotate_key(self, key_id: str, new_ttl_days: int = None) -> Optional[dict]:
        """轮换密钥：保留key_id和权限，生成新密钥值

        旧密钥立即失效，新密钥开始使用。
        建议：先创建新密钥（generate_key），旧密钥宽限期再撤销。
        """
        self.load()  # 调用
        with self._lock:  # 上下文管理
            if key_id not in self._keys:  # 条件判断
                return None  # 返回
            old_info = self._keys[key_id]  # 赋值
            if not old_info.get("enabled", True):  # 条件判断
                return None  # 返回

            # 生成新密钥值
            raw_key = f"baa_{secrets.token_urlsafe(32)}"  # 赋值
            new_hash = self._hash_key(raw_key)  # 赋值

            now = datetime.now(timezone.utc)  # 赋值
            ttl = new_ttl_days or old_info.get("ttl_days", DEFAULT_KEY_TTL_DAYS)  # 赋值
            expires_at = now.timestamp() + ttl * 86400  # 赋值

            encrypted_raw = encrypt_raw_key(raw_key)  # 赋值
            self._keys[key_id]["hash"] = new_hash
            self._keys[key_id]["encrypted_raw"] = encrypted_raw
            self._keys[key_id]["ttl_days"] = ttl
            self._keys[key_id]["expires_at"] = datetime.fromtimestamp(
                expires_at, tz=timezone.utc  # 赋值
            ).isoformat()
            self._keys[key_id]["created_at"] = now.isoformat()

        self.save()  # 调用
        return {  # 返回
            "key_id": key_id,
            "raw_key": raw_key,
            "info": {k: v for k, v in self._keys[key_id].items() if k not in ("hash", "encrypted_raw")},
        }

    def delete_key(self, key_id: str) -> bool:
        """删除密钥（不可恢复）"""
        self._reload()  # 调用
        with self._lock:  # 上下文管理
            if key_id not in self._keys:  # 条件判断
                return False  # 返回
            del self._keys[key_id]  # 删除
            self._usage.pop(key_id, None)  # 调用
        self.save()  # 调用
        return True  # 返回

    # ── 用量统计 ──────────────────────────────────────────

    def record_usage(self, raw_key: str):
        """记录API调用"""
        self.load()  # 调用
        # 环境变量key不记录
        if self._env_key and hmac.compare_digest(raw_key, self._env_key):  # 条件判断
            return  # 返回

        key_id = None  # 赋值
        for kid, info in self._keys.items():  # 循环
            if self._verify_key(raw_key, info["hash"]):  # 条件判断
                key_id = kid  # 赋值
                break  # 跳出循环

        if not key_id:  # 条件判断
            return  # 返回

        now = time.time()  # 赋值
        with self._lock:  # 上下文管理
            usage = self._usage.setdefault(key_id, {"calls": 0, "last_used": None, "per_minute": []})  # 赋值
            usage["calls"] += 1
            usage["last_used"] = datetime.now(timezone.utc).isoformat()
            # 每分钟计数（保留最近5分钟）
            minute_bucket = int(now // 60)  # 赋值
            usage["per_minute"] = [b for b in usage.get("per_minute", [])
                                   if b[0] > minute_bucket - 5]  # 条件判断
            usage["per_minute"].append((minute_bucket, now))

    def get_usage_stats(self, key_id: str = None) -> dict:
        """获取用量统计"""
        self.load()  # 调用
        if key_id:  # 条件判断
            usage = self._usage.get(key_id, {})  # 赋值
            key_info = self._keys.get(key_id, {})  # 赋值
            if not key_info:  # 条件判断
                return {}  # 返回
            return {  # 返回
                "key_id": key_id,
                "label": key_info.get("label", ""),
                "permission": key_info.get("permission", ""),
                "total_calls": usage.get("calls", 0),
                "last_used": usage.get("last_used"),
                "created_at": key_info.get("created_at"),
                "expires_at": key_info.get("expires_at"),
                "enabled": key_info.get("enabled", True),
            }

        stats = {}  # 赋值
        for kid in self._keys:  # 循环
            stats[kid] = self.get_usage_stats(kid)  # 赋值
        return stats  # 返回

    def check_rate_limit(self, raw_key: str) -> bool:
        """检查是否超限（返回False表示超出限制）"""
        self.load()  # 调用
        # 环境变量key不限制
        if self._env_key and hmac.compare_digest(raw_key, self._env_key):  # 条件判断
            return True  # 返回

        key_info = self.validate_key(raw_key)  # 赋值
        if not key_info:  # 条件判断
            return False  # 返回

        key_id = key_info["key_id"]  # 赋值
        perm = key_info.get("permission", "limited")  # 赋值
        limit = DEFAULT_RATE_LIMIT.get(perm, 10)  # 赋值

        now = time.time()  # 赋值
        minute_bucket = int(now // 60)  # 赋值

        with self._lock:  # 上下文管理
            usage = self._usage.setdefault(key_id, {"calls": 0, "last_used": None, "per_minute": []})  # 赋值
            # 清理旧bucket
            usage["per_minute"] = [b for b in usage.get("per_minute", [])
                                   if b[0] == minute_bucket]  # 条件判断
            return len(usage["per_minute"]) < limit  # 返回

    # ── 清理过期密钥 ──────────────────────────────────────────

    def cleanup_expired(self) -> int:
        """清理过期密钥（标记为disabled），返回清理数"""
        self.load()  # 调用
        now = datetime.now(timezone.utc)  # 赋值
        cleaned = 0  # 赋值
        with self._lock:  # 上下文管理
            for key_id, info in list(self._keys.items()):  # 循环
                expires = info.get("expires_at")  # 赋值
                if expires:  # 条件判断
                    exp_time = datetime.fromisoformat(expires)  # 赋值
                    if exp_time.tzinfo is None:  # 条件判断
                        exp_time = exp_time.replace(tzinfo=timezone.utc)  # 赋值
                    if now > exp_time:  # 条件判断
                        self._keys[key_id]["enabled"] = False
                        cleaned += 1  # 赋值
        if cleaned:  # 条件判断
            self.save()  # 调用
        return cleaned  # 返回

    # ── 从环境变量初始化 ──────────────────────────────────

    def ensure_env_key_exists(self):
        """确保环境变量中的API Key已在管理器中注册"""
        if not self._env_key:  # 条件判断
            return None  # 返回
        self.load()  # 调用

        # 检查是否已存在
        for info in self._keys.values():  # 循环
            if info.get("label") == "env-key":  # 条件判断
                return info.get("key_id")  # 返回

        # 注册
        raw_key = self._env_key  # 赋值
        key_hash = self._hash_key(raw_key)  # 赋值
        key_id = "key_env_admin"  # 赋值

        key_info = {  # 赋值
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
        with self._lock:  # 上下文管理
            self._keys[key_id] = key_info  # 赋值
            self._usage[key_id] = {"calls": 0, "last_used": None, "per_minute": []}
        self.save()  # 调用
        return key_id  # 返回


# ── 全局单例 ──────────────────────────────────────────────

_key_manager = None  # 赋值


def get_key_manager() -> ApiKeyManager:
    global _key_manager  # 全局变量
    if _key_manager is None:  # 条件判断
        _key_manager = ApiKeyManager()  # 赋值
        _key_manager.load()  # 调用
        _key_manager.ensure_env_key_exists()  # 调用
        _key_manager.cleanup_expired()  # 调用
    return _key_manager  # 返回
