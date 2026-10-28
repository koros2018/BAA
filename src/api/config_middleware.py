"""生产配置管理（E4-T4）。

提供两个能力：
1. 启动时校验关键环境变量，输出健康报告（warnings/errors）
2. /api/v1/admin/config 端点：返回脱敏后的当前配置摘要，供运维诊断与审计

敏感字段（BAA_API_KEY / BAA_AUTH_SECRET / BAA_DATABASE_URL 中的密码段）
一律脱敏展示（首尾各保留 4 字符，中间掩码）。
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

# ── 配置元数据定义 ───────────────────────────────────────────────
# (变量名, 是否必填, 默认值, 合法值校验函数, 提示文案)
_CONFIG_SCHEMA: List[tuple] = [
    # 安全基线（T-C4）
    ("BAA_ALLOW_ANONYMOUS", True, "0", lambda v: v in ("0", "1"),
     "生产必须为 0；1=匿名放行（仅开发/E2E）"),
    ("BAA_PDF_ISOLATION", True, "1", lambda v: v in ("0", "1"),
     "AGPL 进程隔离开关，生产建议开启"),
    ("BAA_VISION_ENABLED", False, "false", lambda v: v.lower() in ("true", "false", "1", "0"),
     "YOLO/光栅视觉层开关，生产必须 false"),
    # 认证
    ("BAA_API_KEY", False, "", lambda v: len(v) >= 32 or v == "",
     "管理密钥，生产建议 ≥32 字符"),
    ("BAA_AUTH_SECRET", False, "", lambda v: len(v) >= 16 or v == "",
     "内部认证密钥，逗号分隔多个"),
    # 日志与可观测
    ("BAA_LOG_FORMAT", False, "text", lambda v: v in ("text", "json"),
     "结构化日志格式（text/json），生产推荐 json"),
    # 数据库
    ("BAA_DATABASE_URL", True, "", lambda v: len(v) > 0,
     "数据库连接串（PostgreSQL/SQLite）"),
    # 运行时
    ("BAA_PORT", False, "8000", lambda v: 1 <= int(v or 8000) <= 65535,
     "HTTP 服务端口"),
    ("BAA_WORKERS", False, "4", lambda v: int(v or 4) in (1, 2, 4, 8, 16),
     "Gunicorn worker 数（1/2/4/8/16）"),
    ("BAA_QUEUE_NAMESPACE", False, "default", lambda v: len(v) > 0,
     "审查队列命名空间（多副本共享存储时区分）"),
    ("BAA_DATA_DIR", False, "", lambda v: len(v) > 0 or True,
     "数据目录（文件/密钥/日志/模型）"),
    ("BAA_CORRECTION_MODE", False, "hybrid", lambda v: v in ("rule", "hybrid", "ml"),
     "纠正模式：rule/hybrid/ml"),
]

# 敏感字段：内容需脱敏后展示
_SENSITIVE_KEYS = {"BAA_API_KEY", "BAA_AUTH_SECRET", "BAA_DATABASE_URL"}


def _mask(value: str) -> str:
    """首尾各留 4 字符，中间掩码为 *。空值返回 '***'。"""
    if not value:
        return "***"
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def validate_env() -> Dict[str, Any]:
    """校验环境变量，返回报告。

    Returns:
        {
            "valid": bool,
            "errors": [{"key": ..., "msg": ...}],
            "warnings": [{"key": ..., "msg": ...}],
            "summary": {<env_key>: <masked_value_or_default>},
        }
    """
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    summary: Dict[str, Any] = {}

    for key, required, default, validator, hint in _CONFIG_SCHEMA:
        raw = os.getenv(key, "")
        value = raw if raw else default

        # 脱敏写入 summary
        if key in _SENSITIVE_KEYS:
            summary[key] = _mask(raw) if raw else (default if default else "")
        else:
            summary[key] = value

        # 必填校验
        if required and not raw:
            errors.append({"key": key, "msg": f"必填但未设置（建议值：{default}）。{hint}"})
            continue

        # 合法值校验
        if raw and not validator(raw):
            warnings.append({"key": key, "msg": f"值 '{raw}' 可能不合法（{hint}）"})

        # 生产安全兜底警告
        if key == "BAA_ALLOW_ANONYMOUS" and raw == "1":
            warnings.append({"key": key, "msg": "匿名放行已开启，生产环境存在安全风险"})
        if key == "BAA_VISION_ENABLED" and raw.lower() in ("true", "1"):
            warnings.append({"key": key, "msg": "光栅视觉层已启用，生产环境不建议开启"})
        if key == "BAA_API_KEY" and raw and len(raw) < 32:
            warnings.append({"key": key, "msg": "API_KEY 长度 < 32，建议至少 32 字符"})
        if key == "BAA_LOG_FORMAT" and raw == "text":
            warnings.append({"key": key, "msg": "日志未启用结构化格式，生产建议设为 json"})

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": summary,
    }


def get_config_endpoint_payload() -> Dict[str, Any]:
    """返回 /api/v1/admin/config 的响应负载（脱敏，含健康报告）。"""
    report = validate_env()
    return {
        "status": "success",
        "health": report,
        "config": {
            "env_count": sum(1 for k, _, _, _, _ in _CONFIG_SCHEMA if os.getenv(k)),
            "schema_keys": [k for k, _, _, _, _ in _CONFIG_SCHEMA],
            "summary": report["summary"],
        },
    }
