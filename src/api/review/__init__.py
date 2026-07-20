"""
审查模块 — 包入口
"""

from fastapi import APIRouter
from src.api.api_globals import *  # noqa: F401, F403
from src.api import api_globals as _api_globals


# 惰性获取引擎引用
def _get_dp():
    return _api_globals._drawing_parser


def _get_sa():
    return _api_globals._semantic_analyzer


def _get_fr():
    return _api_globals._func_registry


def _get_sr():
    return _api_globals._spec_repo


def _get_aa():
    return _api_globals._attribution_analyzer


def _get_pool():
    return _api_globals.ENGINE_THREAD_POOL


def _get_rq():
    return _api_globals._review_queue


def _get_pc():
    return _api_globals._persistent_cache


def _get_rc():
    return _api_globals._review_cache


def _get_rc_max():
    return _api_globals._REVIEW_CACHE_MAX


make_cache_key = _api_globals.make_cache_key

# 从 api_globals 重新导出审查路由需要的变量
verify_api_key = _api_globals.verify_api_key
SUPPORTED_FORMATS = _api_globals.SUPPORTED_FORMATS
MAX_FILE_SIZE = _api_globals.MAX_FILE_SIZE
MAX_FILE_SIZE_MB = _api_globals.MAX_FILE_SIZE_MB
generate_file_id = _api_globals.generate_file_id
store_file = _api_globals.store_file
get_file_path = _api_globals.get_file_path
MODELS_DIR = _api_globals.MODELS_DIR

router = APIRouter()

from . import review_routes
from . import render_routes
from . import compare_routes
from . import batch_routes
from . import history_routes
