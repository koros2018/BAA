"""pytest 配置：确保项目路径在 sys.path 中"""
import sys
import os

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 赋值
if PROJECT_ROOT not in sys.path:  # 判断
    sys.path.insert(0, PROJECT_ROOT)  # 调用
