"""pytest 配置：确保项目路径在 sys.path 中"""
import sys  # import
import os  # stdlib: filesystem ops

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # path operation
if PROJECT_ROOT not in sys.path:  # check: membership test
    sys.path.insert(0, PROJECT_ROOT)  # sys path
