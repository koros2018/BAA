"""启动后端服务（带 BAA_ALLOW_ANONYMOUS=1）。"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BAA_ALLOW_ANONYMOUS"] = "1"
import uvicorn
uvicorn.run("src.api.baa_api:app", host="127.0.0.1", port=8000, log_level="warning")
