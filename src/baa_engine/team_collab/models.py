"""
BAA 协作模块 — 模型 re-export shim（T-C1 统一数据层）

模型已统一迁至 src/baa_engine/db/models/collab.py（共享统一 Base，Alembic 管理建表）。
本文件仅 re-export 保持既有 import 路径兼容；请勿在此新增模型定义，
避免出现两份漂移的模型。
"""

from src.baa_engine.db.models.collab import (  # noqa: F401
    Base,
    COLLAB_SECRET,
    DEFAULT_COLLAB_DIR,
    DEFAULT_DB_PATH,
    TOKEN_EXPIRE_HOURS,
    ApprovalFlow,
    ApprovalStatus,
    ApprovalStep,
    CommentType,
    Project,
    ProjectMember,
    ProjectPermission,
    RectificationRecord,
    ReviewComment,
    ReviewSession,
    ReviewStatus,
    Team,
    TeamMember,
    TeamRole,
    User,
    UserRole,
    REVIEW_STATUS_TRANSITIONS,
)
