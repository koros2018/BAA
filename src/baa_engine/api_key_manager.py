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

import secrets  # import
import hashlib  # stdlib: hashing
import hmac  # import
import json  # stdlib: JSON
import time  # stdlib: timing
import os  # stdlib: filesystem ops
import base64  # stdlib: base64
import threading  # stdlib: threading
from pathlib import Path  # import: path utils
from datetime import datetime, timezone  # import
from typing import Optional, Dict, List  # typing: type hints

# ── AES-GCM 加密（密钥可恢复，用于前端展示） ──────────────

from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # import

# 用于加密 raw_key 的主密钥（从环境变量派生，或自动生成一个持久化的）
_ENCRYPTION_MASTER_KEY = None  # assignment
_ENCRYPTION_KEY_LOCK = threading.Lock()  # function call


def _get_encryption_key() -> bytes:  # function: def _get_encryption_key() -> bytes:
    """获取/初始化 AES-256 主密钥（32 bytes）

    优先级：
    1. 环境变量 BAA_KEY_ENCRYPTION_KEY（32字节 hex）
    2. 持久化存储的密钥文件 data/.key_encryption.key
    3. 自动生成并保存
    """
    global _ENCRYPTION_MASTER_KEY  # 全局变量
    # 条件分支：if _ENCRYPTION_MASTER_KEY is not None
    if _ENCRYPTION_MASTER_KEY is not None:  # check: value is not None
        return _ENCRYPTION_MASTER_KEY  # return

    # 上下文管理器
    with _ENCRYPTION_KEY_LOCK:  # 上下文管理
        # 条件分支：if _ENCRYPTION_MASTER_KEY is not None
        if _ENCRYPTION_MASTER_KEY is not None:  # check: value is not None
            return _ENCRYPTION_MASTER_KEY  # return

        # 1. 环境变量
        env_key = os.getenv("BAA_KEY_ENCRYPTION_KEY", "")  # function call
        if env_key:  # condition: env_key:
            try:  # 尝试
                _ENCRYPTION_MASTER_KEY = bytes.fromhex(env_key)  # function call
                if len(_ENCRYPTION_MASTER_KEY) == 32:  # check: length
                    return _ENCRYPTION_MASTER_KEY  # return
            # 异常处理
            except ValueError:  # 捕获异常
                pass  # 占位

        # 2. 持久化密钥文件
        storage_dir = Path(__file__).resolve().parent.parent.parent / "data"  # function call
        key_file = storage_dir / ".key_encryption.key"  # assignment
        if key_file.exists():  # condition: key_file.exists():
            raw = key_file.read_bytes().strip()  # function call
            if len(raw) == 32:  # check: length
                _ENCRYPTION_MASTER_KEY = raw  # assignment
                return _ENCRYPTION_MASTER_KEY  # return

        # 3. 自动生成
        storage_dir.mkdir(parents=True, exist_ok=True)  # function call
        new_key = AESGCM.generate_key(bit_length=256)  # function call
        key_file.write_bytes(new_key)  # function call
        os.chmod(str(key_file), 0o600)  # 仅 owner 可读写
        _ENCRYPTION_MASTER_KEY = new_key  # assignment
        return _ENCRYPTION_MASTER_KEY  # return


def encrypt_raw_key(raw_key: str) -> str:  # function: def encrypt_raw_key(raw_key: str) -> str:
    """AES-GCM 加密 raw_key，返回 base64 编码密文"""
    key = _get_encryption_key()  # function call
    aesgcm = AESGCM(key)  # function call
    nonce = os.urandom(12)  # GCM 推荐 96-bit nonce
    ciphertext = aesgcm.encrypt(nonce, raw_key.encode("utf-8"), None)  # function call
    # 格式: base64(nonce + ciphertext)
    return base64.b64encode(nonce + ciphertext).decode("ascii")  # return


def decrypt_raw_key(
    encrypted: str,
) -> Optional[str]:  # function: def decrypt_raw_key(encrypted: str) -> Optional[str]:
    """解密 raw_key，失败返回 None"""
    # 异常保护
    try:  # 尝试
        key = _get_encryption_key()  # function call
        data = base64.b64decode(encrypted)  # function call
        nonce = data[:12]  # assignment
        ciphertext = data[12:]  # assignment
        aesgcm = AESGCM(key)  # function call
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)  # function call
        return plaintext.decode("utf-8")  # return
    # 异常处理
    except Exception:  # 捕获异常
        return None  # return: None


# ── 权限等级 ──────────────────────────────────────────────


class ApiKeyPermission:  # class definition
    """API 密钥权限等级定义

    四级权限模型：
    - admin：完全控制（创建/撤销密钥、管理），仅限运维人员
    - write：可上传图纸、发起审查，用于集成服务
    - read：可查询订单/结果，用于监控和前端展示
    - limited：只读+限制调用频率，用于第三方对接

    权限的校验在 check_rate_limit 和 validate_key 中联动实现，
    admin 通道不触发频率限制。
    """

    ADMIN = "admin"  # 完全控制（创建/撤销密钥、管理）
    WRITE = "write"  # 可上传图纸、发起审查
    READ = "read"  # 可查询订单/结果
    LIMITED = "limited"  # 只读+限制调用频率

    ALL = (ADMIN, WRITE, READ, LIMITED)  # function call

    @classmethod  # code
    def validate(cls, perm: str) -> bool:  # function: def validate(cls, perm: str) -> bool:
        """校验权限等级是否合法"""
        return perm in cls.ALL  # return


# ── 默认配置 ──────────────────────────────────────────────

DEFAULT_KEY_TTL_DAYS = 90  # 密钥默认有效期90天
DEFAULT_RATE_LIMIT = {  # 每密钥每分钟限制
    "admin": 1000,  # 字段
    "write": 100,  # 字段
    "read": 60,  # 字段
    "limited": 10,  # 字段
}  # code
DEFAULT_STORAGE_PATH = "data/api_keys.json"  # assignment


# ── 密钥管理器 ──────────────────────────────────────────────


class ApiKeyManager:  # class definition
    """API 密钥全生命周期管理

    核心功能：
    - 生成：自动生成安全密钥（secrets.token_urlsafe），AES-GCM 加密存储
    - 验证：SHA-256 哈希 + hmac 常量时间比较，防止计时攻击
    - 过期：可配置 TTL，到期自动禁用
    - 权限：四级权限模型（admin/write/read/limited）
    - 用量：调用计数、最后使用时间、每分钟频率限制
    - 持久化：JSON 文件 + 原子写入（先写 tmp 再 rename）

    安全设计：
    - raw_key 在创建时返回一次，后续仅存储 AES-GCM 加密密文
    - 存储的 key_hash 是单向哈希，不可逆向还原
    - 环境变量 BAA_API_KEY 作为 admin 通道，绕过文件存储
    - 主密钥 BAA_KEY_ENCRYPTION_KEY 用于 AES-256 加密
    """

    def __init__(
        self, storage_path: str = None, env_key: str = None
    ):  # function: def __init__(self, storage_path: str = None, env_key: str =
        """初始化 API 密钥管理器

        Args:
            storage_path: JSON 持久化文件路径，默认 data/api_keys.json
            env_key: 环境变量密钥，用于 admin 通道（绕过文件存储）
        """
        self._lock = threading.Lock()  # function call
        self._storage_path = storage_path or os.getenv(  # assignment
            "BAA_API_KEYS_PATH",  # code
            str(
                Path(__file__).resolve().parent.parent.parent / DEFAULT_STORAGE_PATH
            ),  # function call
        )  # code
        self._keys: Dict[str, dict] = {}  # key_id → key_info
        self._usage: Dict[str, dict] = {}  # key_id → {calls, last_used, per_minute}
        self._env_key = env_key or os.getenv("BAA_API_KEY", "")  # function call
        self._loaded = False  # assignment

    # ── 持久化 ──────────────────────────────────────────

    def _ensure_storage_dir(self):  # function: def _ensure_storage_dir(self):
        """确保持久化存储目录存在

        在首次写入前调用，避免 FileNotFoundError。
        使用 parents=True 递归创建多级目录。
        """
        Path(self._storage_path).parent.mkdir(parents=True, exist_ok=True)  # function call

    def _hash_key(self, raw_key: str) -> str:  # function: def _hash_key(self, raw_key: str) -> str:
        """对API Key做单向哈希存储"""
        return hashlib.sha256(raw_key.encode()).hexdigest()  # return

    def _verify_key(
        self, raw_key: str, stored_hash: str
    ) -> bool:  # function: def _verify_key(self, raw_key: str, stored_hash: str) -> boo
        """使用常量时间比较验证 API Key

        使用 hmac.compare_digest 而非 == 的原因是：
        防止计时攻击（timing attack），避免攻击者通过
        比较耗时差异逐位猜测密钥哈希值。
        """
        return hmac.compare_digest(self._hash_key(raw_key), stored_hash)  # return

    def load(self):  # function: def load(self):
        """从持久化存储加载密钥"""
        # 条件分支：if self._loaded
        if self._loaded:  # condition: self._loaded:
            return  # code
        self._reload()  # function call

    def _reload(self):  # function: def _reload(self):
        """强制从文件重新加载（跳过 _loaded 短路）"""
        self._ensure_storage_dir()  # function call
        # 条件分支：if os.path.exists(self._storage_path)
        if os.path.exists(self._storage_path):  # check: OR condition
            # 异常保护
            try:  # 尝试
                # 上下文管理器
                with open(self._storage_path) as f:  # 上下文管理
                    data = json.load(f)  # function call
                # 上下文管理器
                with self._lock:  # 上下文管理
                    self._keys = data.get("keys", {})  # function call
                    self._usage = data.get("usage", {})  # function call
            # 异常处理
            except (json.JSONDecodeError, IOError):  # 捕获异常
                pass  # 占位
        self._loaded = True  # assignment

    def save(self):  # function: def save(self):
        """持久化存储到文件"""
        self._ensure_storage_dir()  # function call
        # 上下文管理器
        with self._lock:  # 上下文管理
            data = {  # assignment
                "keys": self._keys,  # 字段
                "usage": self._usage,  # 字段
                "updated_at": datetime.now(timezone.utc).isoformat(),  # 字段
            }  # code
        # 原子写入：先写临时文件再rename
        tmp = self._storage_path + ".tmp"  # assignment
        with open(tmp, "w") as f:  # 上下文
            json.dump(data, f, indent=2, ensure_ascii=False)  # function call
        os.replace(tmp, self._storage_path)  # function call

    # ── 密钥生成 ──────────────────────────────────────────

    def generate_key(  # function: def generate_key(
        self,  # 解包
        permission: str = "write",  # assignment
        ttl_days: int = None,  # assignment
        label: str = "",  # assignment
        created_by: str = "system",  # assignment
    ) -> dict:  # code
        """生成新 API Key

        Args:
            permission: 权限等级
            ttl_days: 有效期天数（默认90天）
            label: 用途标签（如"生产-前端"、"测试-张三"）
            created_by: 创建者标识

        Returns:
            {"key_id": str, "raw_key": str, "info": dict}
        """
        self.load()  # function call
        # 条件分支：if not ApiKeyPermission.validate(permission)
        if not ApiKeyPermission.validate(permission):  # check: negated condition
            raise ValueError(f"无效权限等级: {permission}")  # 抛出

        ttl = ttl_days or DEFAULT_KEY_TTL_DAYS  # assignment
        raw_key = f"baa_{secrets.token_urlsafe(32)}"  # function call
        key_hash = self._hash_key(raw_key)  # function call
        key_id = f"key_{secrets.token_hex(8)}"  # function call

        now = datetime.now(timezone.utc)  # function call
        expires_at = now.timestamp() + ttl * 86400  # function call

        # AES-GCM 加密存储 raw_key（前端可恢复查看/复制）
        encrypted_raw = encrypt_raw_key(raw_key)  # function call

        key_info = {  # assignment
            "key_id": key_id,  # 字段
            "hash": key_hash,  # 字段
            "encrypted_raw": encrypted_raw,  # AES-GCM 密文，可解密为原始密钥
            "permission": permission,  # 字段
            "label": label,  # 字段
            "created_by": created_by,  # 字段
            "created_at": now.isoformat(),  # 字段
            "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),  # 字段
            "ttl_days": ttl,  # 字段
            "enabled": True,  # 字段
            "last_used": None,  # 字段
            "calls": 0,  # 字段
        }  # code

        # 上下文管理器
        with self._lock:  # 上下文管理
            self._keys[key_id] = key_info  # assignment
            self._usage[key_id] = {"calls": 0, "last_used": None, "per_minute": []}  # 操作

        self.save()  # function call

        # 返回时不包含hash和encrypted_raw
        return_info = {
            k: v for k, v in key_info.items() if k not in ("hash", "encrypted_raw")
        }  # assignment
        return {  # return: dict
            "key_id": key_id,  # 字段
            "raw_key": raw_key,  # 创建时返回，后续可通过 decrypt 恢复
            "info": return_info,  # 字段
        }  # code

    def generate_admin_key(self) -> dict:  # function: def generate_admin_key(self) -> dict:
        """生成初始admin密钥（从环境变量加载时调用）"""
        return self.generate_key(  # return: self
            permission="admin",  # assignment
            ttl_days=365,  # assignment
            label="admin-initial",  # assignment
            created_by="system",  # assignment
        )  # code

    # ── 密钥验证 ──────────────────────────────────────────

    def validate_key(
        self, raw_key: str
    ) -> Optional[dict]:  # function: def validate_key(self, raw_key: str) -> Optional[dict]:
        """验证API Key，返回key_info（无hash）或None"""
        self.load()  # function call

        # 先检查环境变量密钥（管理员通道）
        if self._env_key and hmac.compare_digest(raw_key, self._env_key):  # check: AND condition
            return {  # return: dict
                "key_id": "__env__",  # 字段
                "permission": "admin",  # 字段
                "label": "env-key",  # 字段
                "enabled": True,  # 字段
                "expires_at": None,  # 字段
            }  # code

        # 遍历处理
        for key_id, info in self._keys.items():  # 循环
            # 条件分支：if not info.get("enabled", True)
            if not info.get("enabled", True):  # check: negated condition
                continue  # 继续循环
            # 条件分支：if self._verify_key(raw_key, info["hash"])
            if self._verify_key(
                raw_key, info["hash"]
            ):  # condition: self._verify_key(raw_key, info["hash"]):
                # 检查过期
                expires = info.get("expires_at")  # function call
                if expires:  # condition: expires:
                    exp_time = datetime.fromisoformat(expires)  # function call
                    if exp_time.tzinfo is None:  # check: value is None
                        exp_time = exp_time.replace(tzinfo=timezone.utc)  # function call
                    # 条件分支：if datetime.now(timezone.utc) > exp_time
                    if datetime.now(timezone.utc) > exp_time:  # check: numeric comparison
                        continue  # 已过期
                return {k: v for k, v in info.items() if k != "hash"}  # return: dict
        return None  # return: None

    # ── 密钥管理 ──────────────────────────────────────────

    def list_keys(
        self, include_disabled: bool = False, include_raw: bool = False
    ) -> List[dict]:  # function: def list_keys(self, include_disabled: bool = False, include_
        """列出所有密钥

        Args:
            include_disabled: 是否包含已禁用的
            include_raw: 是否解密并返回 raw_key（前端密钥详情页使用）
        """
        self.load()  # function call
        result = []  # assignment
        # 遍历处理
        for key_id, info in self._keys.items():  # 循环
            # 条件分支：if not include_disabled and not info.get("enabled", True)
            if not include_disabled and not info.get("enabled", True):  # check: negated condition
                continue  # 继续循环
            entry = {k: v for k, v in info.items() if k != "hash"}  # function call
            # 合并用量
            usage = self._usage.get(key_id, {})  # function call
            entry["calls"] = usage.get("calls", 0)  # 操作
            entry["last_used"] = usage.get("last_used")  # 操作
            # 解密 raw_key（前端可用）
            encrypted = info.get("encrypted_raw", "")  # function call
            if include_raw and encrypted:  # check: AND condition
                raw = decrypt_raw_key(encrypted)  # function call
                entry["raw_key"] = raw if raw else None  # 操作
                entry["has_raw_key"] = raw is not None  # 操作
            # 其他情况处理
            else:  # 否则
                entry["has_raw_key"] = bool(encrypted)  # 操作
            result.append(entry)  # append to list
        return sorted(
            result, key=lambda x: x.get("created_at", ""), reverse=True
        )  # return: sorted list

    def revoke_key(
        self, key_id: str
    ) -> bool:  # function: def revoke_key(self, key_id: str) -> bool:
        """撤销密钥"""
        self._reload()  # function call
        # 上下文管理器
        with self._lock:  # 上下文管理
            # 条件分支：if key_id not in self._keys
            if key_id not in self._keys:  # check: membership test
                return False  # return: boolean
            self._keys[key_id]["enabled"] = False  # 操作
        self.save()  # function call
        return True  # return: boolean

    def rotate_key(
        self, key_id: str, new_ttl_days: int = None
    ) -> Optional[dict]:  # function: def rotate_key(self, key_id: str, new_ttl_days: int = None)
        """轮换密钥：保留key_id和权限，生成新密钥值

        旧密钥立即失效，新密钥开始使用。
        建议：先创建新密钥（generate_key），旧密钥宽限期再撤销。
        """
        self.load()  # function call
        # 上下文管理器
        with self._lock:  # 上下文管理
            # 条件分支：if key_id not in self._keys
            if key_id not in self._keys:  # check: membership test
                return None  # return: None
            old_info = self._keys[key_id]  # assignment
            # 条件分支：if not old_info.get("enabled", True)
            if not old_info.get("enabled", True):  # check: negated condition
                return None  # return: None

            # 生成新密钥值
            raw_key = f"baa_{secrets.token_urlsafe(32)}"  # function call
            new_hash = self._hash_key(raw_key)  # function call

            now = datetime.now(timezone.utc)  # function call
            ttl = new_ttl_days or old_info.get("ttl_days", DEFAULT_KEY_TTL_DAYS)  # function call
            expires_at = now.timestamp() + ttl * 86400  # function call

            encrypted_raw = encrypt_raw_key(raw_key)  # function call
            self._keys[key_id]["hash"] = new_hash  # 操作
            self._keys[key_id]["encrypted_raw"] = encrypted_raw  # 操作
            self._keys[key_id]["ttl_days"] = ttl  # 操作
            self._keys[key_id]["expires_at"] = datetime.fromtimestamp(  # 操作
                expires_at, tz=timezone.utc  # assignment
            ).isoformat()  # function call
            self._keys[key_id]["created_at"] = now.isoformat()  # 操作

        self.save()  # function call
        return {  # return: dict
            "key_id": key_id,  # 字段
            "raw_key": raw_key,  # 字段
            "info": {
                k: v for k, v in self._keys[key_id].items() if k not in ("hash", "encrypted_raw")
            },  # 字段
        }  # code

    def delete_key(
        self, key_id: str
    ) -> bool:  # function: def delete_key(self, key_id: str) -> bool:
        """删除密钥（不可恢复）"""
        self._reload()  # function call
        # 上下文管理器
        with self._lock:  # 上下文管理
            # 条件分支：if key_id not in self._keys
            if key_id not in self._keys:  # check: membership test
                return False  # return: boolean
            del self._keys[key_id]  # 删除
            self._usage.pop(key_id, None)  # pop item
        self.save()  # function call
        return True  # return: boolean

    # ── 用量统计 ──────────────────────────────────────────

    def record_usage(self, raw_key: str):  # function: def record_usage(self, raw_key: str):
        """记录API调用"""
        self.load()  # function call
        # 环境变量key不记录
        if self._env_key and hmac.compare_digest(raw_key, self._env_key):  # check: AND condition
            return  # code

        key_id = None  # assignment
        for kid, info in self._keys.items():  # 循环
            # 条件分支：if self._verify_key(raw_key, info["hash"])
            if self._verify_key(
                raw_key, info["hash"]
            ):  # condition: self._verify_key(raw_key, info["hash"]):
                key_id = kid  # assignment
                break  # 跳出循环

        # 条件分支：if not key_id
        if not key_id:  # check: negated condition
            return  # code

        now = time.time()  # function call
        # 上下文管理器
        with self._lock:  # 上下文管理
            usage = self._usage.setdefault(
                key_id, {"calls": 0, "last_used": None, "per_minute": []}
            )  # function call
            usage["calls"] += 1  # 操作
            usage["last_used"] = datetime.now(timezone.utc).isoformat()  # 操作
            # 每分钟计数（保留最近5分钟）
            minute_bucket = int(now // 60)  # function call
            usage["per_minute"] = [
                b for b in usage.get("per_minute", []) if b[0] > minute_bucket - 5  # 操作
            ]  # check: numeric comparison
            usage["per_minute"].append((minute_bucket, now))  # 操作

    def get_usage_stats(
        self, key_id: str = None
    ) -> dict:  # function: def get_usage_stats(self, key_id: str = None) -> dict:
        """获取用量统计"""
        self.load()  # function call
        # 条件分支：if key_id
        if key_id:  # condition: key_id:
            usage = self._usage.get(key_id, {})  # function call
            key_info = self._keys.get(key_id, {})  # function call
            # 条件分支：if not key_info
            if not key_info:  # check: negated condition
                return {}  # return: dict
            return {  # return: dict
                "key_id": key_id,  # 字段
                "label": key_info.get("label", ""),  # 字段
                "permission": key_info.get("permission", ""),  # 字段
                "total_calls": usage.get("calls", 0),  # 字段
                "last_used": usage.get("last_used"),  # 字段
                "created_at": key_info.get("created_at"),  # 字段
                "expires_at": key_info.get("expires_at"),  # 字段
                "enabled": key_info.get("enabled", True),  # 字段
            }  # code

        stats = {}  # assignment
        # 遍历处理
        for kid in self._keys:  # 循环
            stats[kid] = self.get_usage_stats(kid)  # function call
        return stats  # return

    def check_rate_limit(
        self, raw_key: str
    ) -> bool:  # function: def check_rate_limit(self, raw_key: str) -> bool:
        """检查是否超限（返回False表示超出限制）"""
        self.load()  # function call
        # 环境变量key不限制
        if self._env_key and hmac.compare_digest(raw_key, self._env_key):  # check: AND condition
            return True  # return: boolean

        key_info = self.validate_key(raw_key)  # function call
        if not key_info:  # check: negated condition
            return False  # return: boolean

        key_id = key_info["key_id"]  # assignment
        perm = key_info.get("permission", "limited")  # function call
        limit = DEFAULT_RATE_LIMIT.get(perm, 10)  # function call

        now = time.time()  # function call
        minute_bucket = int(now // 60)  # function call

        # 上下文管理器
        with self._lock:  # 上下文管理
            usage = self._usage.setdefault(
                key_id, {"calls": 0, "last_used": None, "per_minute": []}
            )  # function call
            # 清理旧bucket
            usage["per_minute"] = [
                b for b in usage.get("per_minute", []) if b[0] == minute_bucket  # 操作
            ]  # condition: b[0] == minute_bucket]
            return len(usage["per_minute"]) < limit  # return: count

    # ── 清理过期密钥 ──────────────────────────────────────────

    def cleanup_expired(self) -> int:  # function: def cleanup_expired(self) -> int:
        """清理过期密钥（标记为disabled），返回清理数"""
        self.load()  # function call
        now = datetime.now(timezone.utc)  # function call
        cleaned = 0  # assignment
        # 上下文管理器
        with self._lock:  # 上下文管理
            # 遍历处理
            for key_id, info in list(self._keys.items()):  # 循环
                expires = info.get("expires_at")  # function call
                # 条件分支：if expires
                if expires:  # condition: expires:
                    exp_time = datetime.fromisoformat(expires)  # function call
                    # 条件分支：if exp_time.tzinfo is None
                    if exp_time.tzinfo is None:  # check: value is None
                        exp_time = exp_time.replace(tzinfo=timezone.utc)  # function call
                    # 条件分支：if now > exp_time
                    if now > exp_time:  # check: numeric comparison
                        self._keys[key_id]["enabled"] = False  # 操作
                        cleaned += 1  # accumulate
        # 条件分支：if cleaned
        if cleaned:  # condition: cleaned:
            self.save()  # function call
        return cleaned  # return

    # ── 从环境变量初始化 ──────────────────────────────────

    def ensure_env_key_exists(self):  # function: def ensure_env_key_exists(self):
        """确保环境变量中的API Key已在管理器中注册"""
        if not self._env_key:  # check: negated condition
            return None  # return: None
        self.load()  # function call

        # 检查是否已存在
        for info in self._keys.values():  # 循环
            if info.get("label") == "env-key":  # condition: info.get("label") == "env-key":
                return info.get("key_id")  # return

        # 注册
        raw_key = self._env_key  # assignment
        key_hash = self._hash_key(raw_key)  # function call
        key_id = "key_env_admin"  # assignment

        key_info = {  # assignment
            "key_id": key_id,  # 字段
            "hash": key_hash,  # 字段
            "encrypted_raw": encrypt_raw_key(raw_key),  # 字段
            "permission": "admin",  # 字段
            "label": "env-key",  # 字段
            "created_by": "env",  # 字段
            "created_at": datetime.now(timezone.utc).isoformat(),  # 字段
            "expires_at": None,  # 字段
            "ttl_days": None,  # 字段
            "enabled": True,  # 字段
            "last_used": None,  # 字段
            "calls": 0,  # 字段
        }  # code
        # 上下文管理器
        with self._lock:  # 上下文管理
            self._keys[key_id] = key_info  # assignment
            self._usage[key_id] = {"calls": 0, "last_used": None, "per_minute": []}  # 操作
        self.save()  # function call
        return key_id  # return


# ── 全局单例 ──────────────────────────────────────────────

_key_manager = None  # assignment


def get_key_manager() -> ApiKeyManager:  # function: def get_key_manager() -> ApiKeyManager:
    """获取全局单例的 ApiKeyManager

    单例模式确保整个应用生命周期内只维护一份密钥状态。
    初始化时自动执行：
    1. load() — 从文件加载持久化密钥
    2. ensure_env_key_exists() — 注册环境变量密钥
    3. cleanup_expired() — 清理过期密钥
    """
    global _key_manager  # 全局变量
    # 条件分支：if _key_manager is None
    if _key_manager is None:  # check: value is None
        _key_manager = ApiKeyManager()  # function call
        _key_manager.load()  # function call
        _key_manager.ensure_env_key_exists()  # function call
        _key_manager.cleanup_expired()  # function call
    return _key_manager  # return
