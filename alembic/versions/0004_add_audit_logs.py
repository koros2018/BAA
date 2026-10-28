"""add audit_logs table (E2-T2 系统审计日志)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-27 14:00:00.000000

审计日志记录每次审查/审核操作，用于合规举证和纠纷处理。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('audit_logs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('actor_id', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('actor_role', sa.String(length=20), nullable=False, server_default='system'),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('resource_id', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=False, server_default=''),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs')),
    )
    op.create_index(
        op.f('ix_audit_logs_event'), 'audit_logs', ['event_type'], unique=False
    )
    op.create_index(
        op.f('ix_audit_logs_resource'), 'audit_logs', ['resource_type', 'resource_id'], unique=False
    )
    op.create_index(
        op.f('ix_audit_logs_actor'), 'audit_logs', ['actor_id'], unique=False
    )
    op.create_index(
        op.f('ix_audit_logs_created'), 'audit_logs', ['created_at'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_logs_created'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_actor'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_resource'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_event'), table_name='audit_logs')
    op.drop_table('audit_logs')
