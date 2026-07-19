"""
BAA 协作模块 — ORM 模型与枚举定义
P43: 多用户协作

定义 6 个枚举 + 7 个 SQLAlchemy ORM 模型：
- UserRole / TeamRole / ProjectPermission / CommentType / ApprovalStatus / ReviewStatus
- User / Team / TeamMember / Project / ProjectMember / ReviewSession / ReviewComment
- ApprovalFlow / ApprovalStep
"""

import uuid
import time
import hashlib
import secrets
import os
from enum import Enum

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Text,
    ForeignKey,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import declarative_base, relationship

DEFAULT_COLLAB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "collab",
)
DEFAULT_DB_PATH = os.path.join(DEFAULT_COLLAB_DIR, "baa_collab.db")
COLLAB_SECRET = os.getenv("BAA_COLLAB_SECRET", secrets.token_hex(32))
TOKEN_EXPIRE_HOURS = 72


# 用户角色枚举：admin 管理员 / user 普通用户 / viewer 只读用户
# 用于 API 鉴权时区分操作权限级别
class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


# 团队角色枚举：owner 创建者 / manager 管理者 / member 成员 / guest 访客
# owner 有解散团队权限，manager 可管理成员
class TeamRole(str, Enum):
    OWNER = "owner"
    MANAGER = "manager"
    MEMBER = "member"
    GUEST = "guest"


# 项目权限枚举：owner 所有者 / edit 编辑 / review 审查 / comment 评论 / view 只读
# 越靠前权限越大，按位运算比较
class ProjectPermission(str, Enum):
    OWNER = "owner"
    EDIT = "edit"
    REVIEW = "review"
    COMMENT = "comment"
    VIEW = "view"


# 评论类型枚举：issue 问题 / suggestion 建议 / question 疑问 / approval 审批 / note 备注
# 用于审查评论的快速分类和过滤
class CommentType(str, Enum):
    ISSUE = "issue"
    SUGGESTION = "suggestion"
    QUESTION = "question"
    APPROVAL = "approval"
    NOTE = "note"


# 审批状态枚举：pending 待审 / approved 通过 / rejected 驳回 / revoked 撤回 / skipped 跳过
# 多级审批流程中每个步骤独立状态
class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"
    SKIPPED = "skipped"


# 审查会话状态枚举：draft 草稿 / pending 待审 / in_progress 进行中 / approved 通过 / rejected 驳回 / archived 归档
class ReviewStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


Base = declarative_base()


# 用户模型：存密码哈希而非明文，使用 salt+sha256 散列
# token 字段用于 API 鉴权，72h 过期
class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4())[:12])
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=True)
    display_name = Column(String(128), default="")
    password_hash = Column(String(256), nullable=False)
    role = Column(String(16), default=UserRole.USER.value)
    avatar_url = Column(String(512), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)
    last_login_at = Column(Float, default=0.0)
    token = Column(String(64), default="")
    team_memberships = relationship("TeamMember", back_populates="user", lazy="selectin")
    project_memberships = relationship("ProjectMember", back_populates="user", lazy="selectin")
    comments = relationship("ReviewComment", back_populates="author", lazy="dynamic")
    owned_teams = relationship("Team", back_populates="owner", lazy="dynamic")

# 设置密码：salt 随机生成 16 字节，与密码拼接后 sha256 散列
# 存储格式 salt$hash，防止彩虹表攻击
    def set_password(self, password: str):
        salt = secrets.token_hex(16)
        self.password_hash = f"{salt}${hashlib.sha256((salt + password).encode()).hexdigest()}"

# 验证密码：从存储的 hash 中提取 salt，重新计算后比对
# 返回 False 时上层应记录登录失败次数
    def verify_password(self, password: str) -> bool:
        if "$" not in self.password_hash:
            return False
        salt, stored_hash = self.password_hash.split("$", 1)
        return stored_hash == hashlib.sha256((salt + password).encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "role": self.role,
            "avatar_url": self.avatar_url,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "last_login_at": self.last_login_at,
        }


# 团队模型：owner_id 关联用户表，max_members 限制团队规模
# is_public 控制是否允许外部用户申请加入
class Team(Base):
    __tablename__ = "teams"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4())[:12])
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    max_members = Column(Integer, default=50)
    is_public = Column(Boolean, default=False)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)
    owner = relationship("User", back_populates="owned_teams", lazy="selectin")
    members = relationship(
        "TeamMember", back_populates="team", lazy="selectin", cascade="all, delete-orphan"
    )
    projects = relationship("Project", back_populates="team", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "owner_id": self.owner_id,
            "max_members": self.max_members,
            "is_public": self.is_public,
            "created_at": self.created_at,
            "member_count": len(self.members) if self.members else 0,
        }


# 团队成员关联表：联合唯一约束 (team_id, user_id) 防止重复加入
# invited_by 记录邀请人，用于审计
class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_user"),)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4())[:12])
    team_id = Column(String(36), ForeignKey("teams.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    role = Column(String(16), default=TeamRole.MEMBER.value)
    joined_at = Column(Float, default=time.time)
    invited_by = Column(String(36), nullable=True)
    team = relationship("Team", back_populates="members", lazy="selectin")
    user = relationship("User", back_populates="team_memberships", lazy="selectin")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "team_id": self.team_id,
            "user_id": self.user_id,
            "username": self.user.username if self.user else "",
            "display_name": self.user.display_name if self.user else "",
            "role": self.role,
            "joined_at": self.joined_at,
        }


# 项目模型：关联团队和创建者，building_type/area 用于审查上下文
# tags 字段存 JSON 数组，支持灵活标签过滤
class Project(Base):
    __tablename__ = "projects"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4())[:12])
    name = Column(String(256), nullable=False)
    description = Column(Text, default="")
    team_id = Column(String(36), ForeignKey("teams.id"), nullable=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    building_type = Column(String(64), default="")
    building_area = Column(Float, default=0.0)
    file_count = Column(Integer, default=0)
    review_count = Column(Integer, default=0)
    status = Column(String(16), default="active")
    tags = Column(JSON, default=list)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)
    team = relationship("Team", back_populates="projects", lazy="selectin")
    owner = relationship("User", lazy="selectin")
    members = relationship(
        "ProjectMember", back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    review_sessions = relationship(
        "ReviewSession", back_populates="project", lazy="dynamic", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "team_id": self.team_id,
            "owner_id": self.owner_id,
            "building_type": self.building_type,
            "building_area": self.building_area,
            "file_count": self.file_count,
            "review_count": self.review_count,
            "status": self.status,
            "tags": self.tags,
            "created_at": self.created_at,
            "member_count": len(self.members) if self.members else 0,
        }


# 项目成员关联表：permission 控制成员在项目内的操作权限
# 联合唯一约束防止重复添加
class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_user"),)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4())[:12])
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    permission = Column(String(16), default=ProjectPermission.VIEW.value)
    joined_at = Column(Float, default=time.time)
    project = relationship("Project", back_populates="members", lazy="selectin")
    user = relationship("User", back_populates="project_memberships", lazy="selectin")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "username": self.user.username if self.user else "",
            "display_name": self.user.display_name if self.user else "",
            "permission": self.permission,
            "joined_at": self.joined_at,
        }


# 审查会话模型：一次审查的完整记录，包含审查结果摘要
# file_ids 存 JSON 数组，支持多文件审查
class ReviewSession(Base):
    __tablename__ = "review_sessions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4())[:12])
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    name = Column(String(256), default="")
    description = Column(Text, default="")
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    status = Column(String(16), default=ReviewStatus.DRAFT.value)
    file_ids = Column(JSON, default=list)
    result_summary = Column(JSON, default=dict)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)
    completed_at = Column(Float, default=0.0)
    project = relationship("Project", back_populates="review_sessions", lazy="selectin")
    creator = relationship("User", lazy="selectin")
    comments = relationship(
        "ReviewComment",
        back_populates="review_session",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    approval_flow = relationship(
        "ApprovalFlow", back_populates="review_session", uselist=False, cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "created_by": self.created_by,
            "creator_name": self.creator.display_name if self.creator else "",
            "status": self.status,
            "file_ids": self.file_ids,
            "result_summary": self.result_summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }


# 审查评论模型：支持父子层级（parent_id），clause_id 关联规范条款
# is_resolved 标记已处理，resolved_by 记录处理人
class ReviewComment(Base):
    __tablename__ = "review_comments"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4())[:12])
    review_session_id = Column(String(36), ForeignKey("review_sessions.id"), nullable=False)
    parent_id = Column(String(36), nullable=True)
    author_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    comment_type = Column(String(16), default=CommentType.NOTE.value)
    content = Column(Text, nullable=False)
    clause_id = Column(String(64), nullable=True)
    entity_id = Column(String(64), nullable=True)
    severity = Column(String(8), default="info")
    is_resolved = Column(Boolean, default=False)
    resolved_by = Column(String(36), nullable=True)
    resolved_at = Column(Float, default=0.0)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)
    review_session = relationship("ReviewSession", back_populates="comments", lazy="selectin")
    author = relationship("User", back_populates="comments", lazy="selectin")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "review_session_id": self.review_session_id,
            "parent_id": self.parent_id,
            "author_id": self.author_id,
            "author_name": self.author.display_name if self.author else "",
            "comment_type": self.comment_type,
            "content": self.content,
            "clause_id": self.clause_id,
            "entity_id": self.entity_id,
            "severity": self.severity,
            "is_resolved": self.is_resolved,
            "created_at": self.created_at,
        }


# 审批流程模型：一次审查对应一个审批流程（一对一）
# 多级审批由 ApprovalStep 实现
class ApprovalFlow(Base):
    __tablename__ = "approval_flows"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4())[:12])
    review_session_id = Column(
        String(36), ForeignKey("review_sessions.id"), unique=True, nullable=False
    )
    name = Column(String(128), default="标准审批")
    description = Column(Text, default="")
    status = Column(String(16), default=ApprovalStatus.PENDING.value)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)
    completed_at = Column(Float, default=0.0)
    review_session = relationship("ReviewSession", back_populates="approval_flow", lazy="selectin")
    creator = relationship("User", lazy="selectin")
    steps = relationship(
        "ApprovalStep",
        back_populates="flow",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="ApprovalStep.step_order",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "review_session_id": self.review_session_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "created_by": self.created_by,
            "steps": [s.to_dict() for s in (self.steps or [])],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


# 审批步骤模型：step_order 控制顺序，assignee 指定审批人
# 联合唯一约束 (flow_id, step_order) 防止顺序冲突
class ApprovalStep(Base):
    __tablename__ = "approval_steps"
    __table_args__ = (UniqueConstraint("flow_id", "step_order", name="uq_flow_step"),)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4())[:12])
    flow_id = Column(String(36), ForeignKey("approval_flows.id"), nullable=False)
    step_order = Column(Integer, nullable=False)
    assignee_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    status = Column(String(16), default=ApprovalStatus.PENDING.value)
    comment = Column(Text, default="")
    decided_at = Column(Float, default=0.0)
    created_at = Column(Float, default=time.time)
    flow = relationship("ApprovalFlow", back_populates="steps", lazy="selectin")
    assignee = relationship("User", lazy="selectin")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "flow_id": self.flow_id,
            "step_order": self.step_order,
            "assignee_id": self.assignee_id,
            "assignee_name": self.assignee.display_name if self.assignee else "",
            "status": self.status,
            "comment": self.comment,
            "decided_at": self.decided_at,
            "created_at": self.created_at,
        }
