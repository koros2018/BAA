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

import uuid
import time
import hashlib
import secrets
import os
import threading
from datetime import datetime
from typing import Optional, List, Tuple
from enum import Enum

from sqlalchemy import (
    create_engine,
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

from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session, Session

import logging

logger = logging.getLogger(__name__)

DEFAULT_COLLAB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "collab",
)
DEFAULT_DB_PATH = os.path.join(DEFAULT_COLLAB_DIR, "baa_collab.db")
COLLAB_SECRET = os.getenv("BAA_COLLAB_SECRET", secrets.token_hex(32))
TOKEN_EXPIRE_HOURS = 72


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class TeamRole(str, Enum):
    OWNER = "owner"
    MANAGER = "manager"
    MEMBER = "member"
    GUEST = "guest"


class ProjectPermission(str, Enum):
    OWNER = "owner"
    EDIT = "edit"
    REVIEW = "review"
    COMMENT = "comment"
    VIEW = "view"


class CommentType(str, Enum):
    ISSUE = "issue"
    SUGGESTION = "suggestion"
    QUESTION = "question"
    APPROVAL = "approval"
    NOTE = "note"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"
    SKIPPED = "skipped"


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


Base = declarative_base()


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

    def set_password(self, password: str):
        salt = secrets.token_hex(16)
        self.password_hash = f"{salt}${hashlib.sha256((salt + password).encode()).hexdigest()}"

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
            "resolved_by": self.resolved_by,
            "created_at": self.created_at,
        }


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
    assignee = relationship("User", back_populates=None, lazy="selectin")

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


_PERMISSION_HIERARCHY = {
    ProjectPermission.OWNER.value: 5,
    ProjectPermission.EDIT.value: 4,
    ProjectPermission.REVIEW.value: 3,
    ProjectPermission.COMMENT.value: 2,
    ProjectPermission.VIEW.value: 1,
}
_TEAM_ROLE_HIERARCHY = {
    TeamRole.OWNER.value: 4,
    TeamRole.MANAGER.value: 3,
    TeamRole.MEMBER.value: 2,
    TeamRole.GUEST.value: 1,
}


def _check_permission(user_perm: str, required_perm: str) -> bool:
    return _PERMISSION_HIERARCHY.get(user_perm, 0) >= _PERMISSION_HIERARCHY.get(required_perm, 0)


def _check_team_role(user_role: str, required_role: str) -> bool:
    return _TEAM_ROLE_HIERARCHY.get(user_role, 0) >= _TEAM_ROLE_HIERARCHY.get(required_role, 0)


class CollaborationManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = DEFAULT_DB_PATH):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        if self._initialized:
            return
        self._initialized = True
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._engine = create_engine(
            f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, pool_pre_ping=True
        )
        Base.metadata.create_all(self._engine)
        self._session_factory = scoped_session(sessionmaker(bind=self._engine))
        logger.info(f"[Collab] DB ready: {db_path}")

    def _get_session(self) -> Session:
        return self._session_factory()

    def _close_session(self, session: Session):
        session.close()

    def _generate_token(self, user_id: str) -> str:
        payload = f"{user_id}.{time.time() + TOKEN_EXPIRE_HOURS * 3600}.{COLLAB_SECRET}"
        return hashlib.sha256(payload.encode()).hexdigest()[:32]

    def verify_token(self, token: str) -> Optional[str]:
        session = self._get_session()
        try:
            user = session.query(User).filter(User.token == token, User.is_active == True).first()
            return user.id if user else None
        finally:
            self._close_session(session)

    def register_user(
        self, username: str, password: str, email: str = "", display_name: str = ""
    ) -> Tuple[Optional[dict], str]:
        session = self._get_session()
        try:
            existing = (
                session.query(User)
                .filter((User.username == username) | ((User.email == email) & (User.email != "")))
                .first()
            )
            if existing:
                return None, "用户名或邮箱已存在"
            user = User(username=username, email=email if email else None, display_name=display_name or username)
            user.set_password(password)
            user.token = self._generate_token(user.id)
            session.add(user)
            session.commit()
            logger.info(f"[Collab] 注册用户: {username}")
            result = user.to_dict()
            result["token"] = user.token
            return result, "success"
        except Exception as e:
            session.rollback()
            return None, str(e)
        finally:
            self._close_session(session)

    def login_user(self, username: str, password: str) -> Tuple[Optional[dict], str]:
        session = self._get_session()
        try:
            user = session.query(User).filter(User.username == username).first()
            if not user:
                return None, "用户不存在"
            if not user.verify_password(password):
                return None, "密码错误"
            if not user.is_active:
                return None, "账户已禁用"
            user.last_login_at = time.time()
            user.token = self._generate_token(user.id)
            session.commit()
            result = user.to_dict()
            result["token"] = user.token
            return result, "success"
        finally:
            self._close_session(session)

    def get_user(self, user_id: str) -> Optional[dict]:
        session = self._get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            return user.to_dict() if user else None
        finally:
            self._close_session(session)

    def update_user(self, user_id: str, updates: dict) -> Tuple[Optional[dict], str]:
        session = self._get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return None, "用户不存在"
            for key in ["display_name", "email", "avatar_url"]:
                if key in updates:
                    setattr(user, key, updates[key])
            if "password" in updates:
                user.set_password(updates["password"])
            session.commit()
            return user.to_dict(), "success"
        except Exception as e:
            session.rollback()
            return None, str(e)
        finally:
            self._close_session(session)

    def list_users(self, query: str = "", limit: int = 50) -> List[dict]:
        session = self._get_session()
        try:
            q = session.query(User).filter(User.is_active == True)
            if query:
                q = q.filter(
                    (User.username.ilike(f"%{query}%")) | (User.display_name.ilike(f"%{query}%"))
                )
            return [u.to_dict() for u in q.limit(limit).all()]
        finally:
            self._close_session(session)

    def create_team(
        self, name: str, owner_id: str, description: str = "", is_public: bool = False
    ) -> Tuple[Optional[dict], str]:
        session = self._get_session()
        try:
            team = Team(name=name, owner_id=owner_id, description=description, is_public=is_public)
            session.add(team)
            session.flush()
            member = TeamMember(
                team_id=team.id, user_id=owner_id, role=TeamRole.OWNER.value, invited_by=owner_id
            )
            session.add(member)
            session.commit()
            logger.info(f"[Collab] 创建团队: {name}")
            return team.to_dict(), "success"
        except Exception as e:
            session.rollback()
            return None, str(e)
        finally:
            self._close_session(session)

    def get_team(self, team_id: str) -> Optional[dict]:
        session = self._get_session()
        try:
            team = session.query(Team).filter(Team.id == team_id).first()
            if not team:
                return None
            result = team.to_dict()
            result["members"] = [m.to_dict() for m in (team.members or [])]
            return result
        finally:
            self._close_session(session)

    def list_user_teams(self, user_id: str) -> List[dict]:
        session = self._get_session()
        try:
            memberships = session.query(TeamMember).filter(TeamMember.user_id == user_id).all()
            teams = []
            for m in memberships:
                team = session.query(Team).filter(Team.id == m.team_id).first()
                if team:
                    t = team.to_dict()
                    t["my_role"] = m.role
                    teams.append(t)
            return teams
        finally:
            self._close_session(session)

    def add_team_member(
        self, team_id: str, inviter_id: str, user_id: str, role: str = TeamRole.MEMBER.value
    ) -> Tuple[Optional[dict], str]:
        session = self._get_session()
        try:
            inviter = (
                session.query(TeamMember)
                .filter(TeamMember.team_id == team_id, TeamMember.user_id == inviter_id)
                .first()
            )
            if not inviter or not _check_team_role(inviter.role, TeamRole.MANAGER.value):
                return None, "无权限"
            existing = (
                session.query(TeamMember)
                .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
                .first()
            )
            if existing:
                return None, "用户已是团队成员"
            member = TeamMember(team_id=team_id, user_id=user_id, role=role, invited_by=inviter_id)
            session.add(member)
            session.commit()
            return member.to_dict(), "success"
        except Exception as e:
            session.rollback()
            return None, str(e)
        finally:
            self._close_session(session)

    def remove_team_member(self, team_id: str, requester_id: str, user_id: str) -> Tuple[bool, str]:
        session = self._get_session()
        try:
            requester = (
                session.query(TeamMember)
                .filter(TeamMember.team_id == team_id, TeamMember.user_id == requester_id)
                .first()
            )
            if not requester or not _check_team_role(requester.role, TeamRole.MANAGER.value):
                return False, "无权限"
            target = (
                session.query(TeamMember)
                .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
                .first()
            )
            if not target:
                return False, "成员不存在"
            if target.role == TeamRole.OWNER.value:
                return False, "不能移除团队所有者"
            session.delete(target)
            session.commit()
            return True, "success"
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            self._close_session(session)

    def create_project(
        self,
        name: str,
        owner_id: str,
        team_id: str = "",
        description: str = "",
        building_type: str = "",
        building_area: float = 0.0,
    ) -> Tuple[Optional[dict], str]:
        session = self._get_session()
        try:
            project = Project(
                name=name,
                owner_id=owner_id,
                description=description,
                building_type=building_type,
                building_area=building_area,
            )
            if team_id:
                project.team_id = team_id
                member = (
                    session.query(TeamMember)
                    .filter(TeamMember.team_id == team_id, TeamMember.user_id == owner_id)
                    .first()
                )
                if not member:
                    return None, "用户不属于该团队"
            session.add(project)
            session.flush()
            pm = ProjectMember(
                project_id=project.id, user_id=owner_id, permission=ProjectPermission.OWNER.value
            )
            session.add(pm)
            session.commit()
            logger.info(f"[Collab] 创建项目: {name}")
            return project.to_dict(), "success"
        except Exception as e:
            session.rollback()
            return None, str(e)
        finally:
            self._close_session(session)

    def get_project(self, project_id: str, user_id: str = "") -> Optional[dict]:
        session = self._get_session()
        try:
            project = session.query(Project).filter(Project.id == project_id).first()
            if not project:
                return None
            result = project.to_dict()
            result["members"] = [m.to_dict() for m in (project.members or [])]
            if user_id:
                result["my_permission"] = self._get_project_permission(session, project_id, user_id)
            return result
        finally:
            self._close_session(session)

    def list_user_projects(self, user_id: str, status: str = "active") -> List[dict]:
        session = self._get_session()
        try:
            memberships = (
                session.query(ProjectMember).filter(ProjectMember.user_id == user_id).all()
            )
            project_ids = [m.project_id for m in memberships]
            if not project_ids:
                return []
            q = session.query(Project).filter(Project.id.in_(project_ids))
            if status:
                q = q.filter(Project.status == status)
            return [p.to_dict() for p in q.order_by(Project.updated_at.desc()).all()]
        finally:
            self._close_session(session)

    def list_team_projects(self, team_id: str, user_id: str = "") -> List[dict]:
        session = self._get_session()
        try:
            q = session.query(Project).filter(Project.team_id == team_id)
            if user_id:
                memberships = (
                    session.query(ProjectMember).filter(ProjectMember.user_id == user_id).all()
                )
                allowed_ids = {m.project_id for m in memberships}
                q = q.filter(Project.id.in_(allowed_ids))
            return [p.to_dict() for p in q.order_by(Project.updated_at.desc()).all()]
        finally:
            self._close_session(session)

    def add_project_member(
        self,
        project_id: str,
        requester_id: str,
        user_id: str,
        permission: str = ProjectPermission.VIEW.value,
    ) -> Tuple[Optional[dict], str]:
        session = self._get_session()
        try:
            requester_perm = self._get_project_permission(session, project_id, requester_id)
            if not _check_permission(requester_perm, ProjectPermission.OWNER.value):
                return None, "无权限"
            existing = (
                session.query(ProjectMember)
                .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
                .first()
            )
            if existing:
                return None, "用户已是项目成员"
            pm = ProjectMember(project_id=project_id, user_id=user_id, permission=permission)
            session.add(pm)
            session.commit()
            return pm.to_dict(), "success"
        except Exception as e:
            session.rollback()
            return None, str(e)
        finally:
            self._close_session(session)

    def update_project_member_permission(
        self, project_id: str, requester_id: str, user_id: str, new_permission: str
    ) -> Tuple[bool, str]:
        session = self._get_session()
        try:
            requester_perm = self._get_project_permission(session, project_id, requester_id)
            if not _check_permission(requester_perm, ProjectPermission.OWNER.value):
                return False, "无权限"
            pm = (
                session.query(ProjectMember)
                .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
                .first()
            )
            if not pm:
                return False, "成员不存在"
            if pm.permission == ProjectPermission.OWNER.value:
                return False, "不能修改所有者权限"
            pm.permission = new_permission
            session.commit()
            return True, "success"
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            self._close_session(session)

    def remove_project_member(
        self, project_id: str, requester_id: str, user_id: str
    ) -> Tuple[bool, str]:
        session = self._get_session()
        try:
            requester_perm = self._get_project_permission(session, project_id, requester_id)
            if not _check_permission(requester_perm, ProjectPermission.OWNER.value):
                return False, "无权限"
            pm = (
                session.query(ProjectMember)
                .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
                .first()
            )
            if not pm:
                return False, "成员不存在"
            if pm.permission == ProjectPermission.OWNER.value:
                return False, "不能移除项目所有者"
            session.delete(pm)
            session.commit()
            return True, "success"
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            self._close_session(session)

    def _get_project_permission(self, session: Session, project_id: str, user_id: str) -> str:
        pm = (
            session.query(ProjectMember)
            .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
            .first()
        )
        return pm.permission if pm else ProjectPermission.VIEW.value

    def create_review_session(
        self,
        project_id: str,
        user_id: str,
        name: str = "",
        description: str = "",
        file_ids: List[str] = None,
    ) -> Tuple[Optional[dict], str]:
        session = self._get_session()
        try:
            perm = self._get_project_permission(session, project_id, user_id)
            if not _check_permission(perm, ProjectPermission.EDIT.value):
                return None, "无权限"
            rs = ReviewSession(
                project_id=project_id,
                name=name or f"审查 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                description=description,
                created_by=user_id,
                file_ids=file_ids or [],
            )
            session.add(rs)
            project = session.query(Project).filter(Project.id == project_id).first()
            if project:
                project.review_count = (project.review_count or 0) + 1
            session.commit()
            return rs.to_dict(), "success"
        except Exception as e:
            session.rollback()
            return None, str(e)
        finally:
            self._close_session(session)

    def get_review_session(self, session_id: str, user_id: str = "") -> Optional[dict]:
        session = self._get_session()
        try:
            rs = session.query(ReviewSession).filter(ReviewSession.id == session_id).first()
            if not rs:
                return None
            result = rs.to_dict()
            if user_id:
                result["my_permission"] = self._get_project_permission(
                    session, rs.project_id, user_id
                )
            return result
        finally:
            self._close_session(session)

    def list_review_sessions(self, project_id: str, user_id: str = "") -> List[dict]:
        session = self._get_session()
        try:
            if user_id:
                perm = self._get_project_permission(session, project_id, user_id)
                if not _check_permission(perm, ProjectPermission.VIEW.value):
                    return []
            return [
                s.to_dict()
                for s in session.query(ReviewSession)
                .filter(ReviewSession.project_id == project_id)
                .order_by(ReviewSession.created_at.desc())
                .all()
            ]
        finally:
            self._close_session(session)

    def update_review_session_status(
        self, session_id: str, user_id: str, status: str
    ) -> Tuple[bool, str]:
        session = self._get_session()
        try:
            rs = session.query(ReviewSession).filter(ReviewSession.id == session_id).first()
            if not rs:
                return False, "会话不存在"
            perm = self._get_project_permission(session, rs.project_id, user_id)
            if not _check_permission(perm, ProjectPermission.EDIT.value):
                return False, "无权限"
            old_status = rs.status
            rs.status = status
            if status in (ReviewStatus.APPROVED.value, ReviewStatus.REJECTED.value):
                rs.completed_at = time.time()
            session.commit()
            logger.info(f"[Collab] 审查状态: {session_id} {old_status} -> {status}")
            return True, "success"
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            self._close_session(session)

    def add_comment(
        self,
        review_session_id: str,
        author_id: str,
        content: str,
        comment_type: str = CommentType.NOTE.value,
        parent_id: str = "",
        clause_id: str = "",
        entity_id: str = "",
        severity: str = "info",
    ) -> Tuple[Optional[dict], str]:
        session = self._get_session()
        try:
            rs = session.query(ReviewSession).filter(ReviewSession.id == review_session_id).first()
            if not rs:
                return None, "审查会话不存在"
            perm = self._get_project_permission(session, rs.project_id, author_id)
            if not _check_permission(perm, ProjectPermission.COMMENT.value):
                return None, "无权限"
            comment = ReviewComment(
                review_session_id=review_session_id,
                parent_id=parent_id or None,
                author_id=author_id,
                comment_type=comment_type,
                content=content,
                clause_id=clause_id or None,
                entity_id=entity_id or None,
                severity=severity,
            )
            session.add(comment)
            session.commit()
            return comment.to_dict(), "success"
        except Exception as e:
            session.rollback()
            return None, str(e)
        finally:
            self._close_session(session)

    def list_comments(
        self, review_session_id: str, user_id: str = "", include_resolved: bool = True
    ) -> List[dict]:
        session = self._get_session()
        try:
            if user_id:
                rs = (
                    session.query(ReviewSession)
                    .filter(ReviewSession.id == review_session_id)
                    .first()
                )
                if rs:
                    perm = self._get_project_permission(session, rs.project_id, user_id)
                    if not _check_permission(perm, ProjectPermission.VIEW.value):
                        return []
            q = session.query(ReviewComment).filter(
                ReviewComment.review_session_id == review_session_id
            )
            if not include_resolved:
                q = q.filter(ReviewComment.is_resolved == False)
            return [c.to_dict() for c in q.order_by(ReviewComment.created_at.asc()).all()]
        finally:
            self._close_session(session)

    def resolve_comment(self, comment_id: str, user_id: str) -> Tuple[bool, str]:
        session = self._get_session()
        try:
            comment = session.query(ReviewComment).filter(ReviewComment.id == comment_id).first()
            if not comment:
                return False, "评论不存在"
            rs = (
                session.query(ReviewSession)
                .filter(ReviewSession.id == comment.review_session_id)
                .first()
            )
            if rs:
                perm = self._get_project_permission(session, rs.project_id, user_id)
                if not _check_permission(perm, ProjectPermission.EDIT.value):
                    return False, "无权限"
            comment.is_resolved = True
            comment.resolved_by = user_id
            comment.resolved_at = time.time()
            session.commit()
            return True, "success"
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            self._close_session(session)

    def create_approval_flow(
        self,
        review_session_id: str,
        created_by: str,
        name: str = "标准审批",
        assignee_ids: List[str] = None,
    ) -> Tuple[Optional[dict], str]:
        session = self._get_session()
        try:
            rs = session.query(ReviewSession).filter(ReviewSession.id == review_session_id).first()
            if not rs:
                return None, "审查会话不存在"
            perm = self._get_project_permission(session, rs.project_id, created_by)
            if not _check_permission(perm, ProjectPermission.OWNER.value):
                return None, "无权限"
            if (
                session.query(ApprovalFlow)
                .filter(ApprovalFlow.review_session_id == review_session_id)
                .first()
            ):
                return None, "审批流已存在"
            flow = ApprovalFlow(
                review_session_id=review_session_id, name=name, created_by=created_by
            )
            session.add(flow)
            session.flush()
            for i, aid in enumerate(assignee_ids or []):
                session.add(ApprovalStep(flow_id=flow.id, step_order=i + 1, assignee_id=aid))
            rs.status = ReviewStatus.PENDING.value
            session.commit()
            logger.info(f"[Collab] 创建审批流: {name} ({len(assignee_ids or [])} steps)")
            return flow.to_dict(), "success"
        except Exception as e:
            session.rollback()
            return None, str(e)
        finally:
            self._close_session(session)

    def approve_step(self, step_id: str, user_id: str, comment: str = "") -> Tuple[bool, str]:
        session = self._get_session()
        try:
            step = session.query(ApprovalStep).filter(ApprovalStep.id == step_id).first()
            if not step:
                return False, "步骤不存在"
            if step.assignee_id != user_id:
                return False, "不是当前审批人"
            if step.status != ApprovalStatus.PENDING.value:
                return False, f"状态非待审批: {step.status}"
            step.status = ApprovalStatus.APPROVED.value
            step.comment = comment
            step.decided_at = time.time()
            flow = session.query(ApprovalFlow).filter(ApprovalFlow.id == step.flow_id).first()
            if flow:
                next_step = (
                    session.query(ApprovalStep)
                    .filter(
                        ApprovalStep.flow_id == flow.id,
                        ApprovalStep.step_order == step.step_order + 1,
                        ApprovalStep.status == ApprovalStatus.PENDING.value,
                    )
                    .first()
                )
                if not next_step:
                    flow.status = ApprovalStatus.APPROVED.value
                    flow.completed_at = time.time()
                    rs = (
                        session.query(ReviewSession)
                        .filter(ReviewSession.id == flow.review_session_id)
                        .first()
                    )
                    if rs:
                        rs.status = ReviewStatus.APPROVED.value
            session.commit()
            return True, "success"
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            self._close_session(session)

    def reject_step(self, step_id: str, user_id: str, comment: str = "") -> Tuple[bool, str]:
        session = self._get_session()
        try:
            step = session.query(ApprovalStep).filter(ApprovalStep.id == step_id).first()
            if not step:
                return False, "步骤不存在"
            if step.assignee_id != user_id:
                return False, "不是当前审批人"
            if step.status != ApprovalStatus.PENDING.value:
                return False, f"状态非待审批: {step.status}"
            step.status = ApprovalStatus.REJECTED.value
            step.comment = comment
            step.decided_at = time.time()
            flow = session.query(ApprovalFlow).filter(ApprovalFlow.id == step.flow_id).first()
            if flow:
                flow.status = ApprovalStatus.REJECTED.value
                flow.completed_at = time.time()
                rs = (
                    session.query(ReviewSession)
                    .filter(ReviewSession.id == flow.review_session_id)
                    .first()
                )
                if rs:
                    rs.status = ReviewStatus.REJECTED.value
            session.commit()
            return True, "success"
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            self._close_session(session)

    def get_approval_flow(self, review_session_id: str) -> Optional[dict]:
        session = self._get_session()
        try:
            flow = (
                session.query(ApprovalFlow)
                .filter(ApprovalFlow.review_session_id == review_session_id)
                .first()
            )
            return flow.to_dict() if flow else None
        finally:
            self._close_session(session)

    def get_stats(self) -> dict:
        session = self._get_session()
        try:
            return {
                "users": session.query(User).count(),
                "teams": session.query(Team).count(),
                "active_projects": session.query(Project)
                .filter(Project.status == "active")
                .count(),
                "review_sessions": session.query(ReviewSession).count(),
                "comments": session.query(ReviewComment).count(),
            }
        finally:
            self._close_session(session)
