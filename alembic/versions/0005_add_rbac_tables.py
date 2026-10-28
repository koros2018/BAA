"""add rbac_roles and rbac_role_members tables (E3-T3 接口级 RBAC)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-27 15:00:00.000000

角色表支持将多个 API key 聚合到角色，便于批量权限管理。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('rbac_roles',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('permission_level', sa.String(length=20), nullable=False, server_default='read'),
        sa.Column('scopes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_rbac_roles')),
    )
    op.create_index(
        op.f('ix_rbac_roles_name'), 'rbac_roles', ['name'], unique=True
    )

    op.create_table('rbac_role_members',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('role_id', sa.String(length=64), nullable=False),
        sa.Column('key_id', sa.String(length=64), nullable=False),
        sa.Column('granted_by', sa.String(length=64), nullable=False, server_default='system'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_rbac_role_members')),
        sa.ForeignKeyConstraint(['role_id'], [op.f('rbac_roles.id')], name=op.f('fk_rbac_role_members_role')),
    )
    op.create_index(
        op.f('ix_rbac_role_members_role'), 'rbac_role_members', ['role_id'], unique=False
    )
    op.create_index(
        op.f('ix_rbac_role_members_key'), 'rbac_role_members', ['key_id'], unique=False
    )
    op.create_index(
        op.f('uq_role_member'), 'rbac_role_members', ['role_id', 'key_id'], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f('uq_role_member'), table_name='rbac_role_members')
    op.drop_index(op.f('ix_rbac_role_members_key'), table_name='rbac_role_members')
    op.drop_index(op.f('ix_rbac_role_members_role'), table_name='rbac_role_members')
    op.drop_table('rbac_role_members')
    op.drop_index(op.f('ix_rbac_roles_name'), table_name='rbac_roles')
    op.drop_table('rbac_roles')
