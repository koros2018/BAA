# scripts/config.py
"""BAA API 配置"""

import os

# BAA 服务地址（默认本地）
BAA_API_BASE = os.getenv("BAA_API_BASE", "http://localhost:8000")

# BAA API 密钥
BAA_API_KEY = os.getenv("BAA_API_KEY", "")

# 默认建筑类型
BAA_DEFAULT_BUILDING_TYPE = os.getenv("BAA_DEFAULT_BUILDING_TYPE", "civil")