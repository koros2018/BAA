"""
BAA 多用户协作引擎
P43: 团队审查 + 评论 + 审批流

功能：
- 用户注册/登录/权限管理（User + Role）
- 团队管理（Team + TeamMember）
- 项目共享与权限（Project + ProjectMember）
- 审查会话与评论（ReviewSession + ReviewComment）
- 审批流（ApprovalFlow + ApprovalStep）
- 数据持久化：SQLite via SQLAlchemy
"""

from .models import (
    Base,
    UserRole,
    TeamRole,
    ProjectPermission,
    CommentType,
    ApprovalStatus,
    ReviewStatus,
    User,
    Team,
    TeamMember,
    Project,
    ProjectMember,
    ReviewSession,
    ReviewComment,
    ApprovalFlow,
    ApprovalStep,
    DEFAULT_COLLAB_DIR,
    DEFAULT_DB_PATH,
    COLLAB_SECRET,
    TOKEN_EXPIRE_HOURS,
)
from .manager import CollaborationManager

__all__ = [
    "Base",
    "UserRole",
    "TeamRole",
    "ProjectPermission",
    "CommentType",
    "ApprovalStatus",
    "ReviewStatus",
    "User",
    "Team",
    "TeamMember",
    "Project",
    "ProjectMember",
    "ReviewSession",
    "ReviewComment",
    "ApprovalFlow",
    "ApprovalStep",
    "DEFAULT_COLLAB_DIR",
    "DEFAULT_DB_PATH",
    "COLLAB_SECRET",
    "TOKEN_EXPIRE_HOURS",
    "CollaborationManager",
]
