"""stateless tables: rate_limit_buckets / api_keys / api_key_usage / review_tasks (T-C2)

并发与扩展（C2）新增四表：
- rate_limit_buckets：跨副本共享的固定窗口限流计数桶
- api_keys / api_key_usage：API 密钥与用量（跨副本可见）
- review_tasks：审查任务队列（原子认领 + 全局状态可见）

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('rate_limit_buckets',
    sa.Column('bucket_key', sa.String(length=200), nullable=False),
    sa.Column('window_start', sa.Integer(), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('bucket_key', name=op.f('pk_rate_limit_buckets'))
    )
    with op.batch_alter_table('rate_limit_buckets', schema=None) as batch_op:
        batch_op.create_index('idx_rl_expires_at', ['expires_at'], unique=False)

    op.create_table('api_keys',
    sa.Column('key_id', sa.String(length=64), nullable=False),
    sa.Column('key_hash', sa.String(length=128), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('record', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('key_id', name=op.f('pk_api_keys'))
    )

    op.create_table('api_key_usage',
    sa.Column('key_id', sa.String(length=64), nullable=False),
    sa.Column('calls', sa.Integer(), nullable=False),
    sa.Column('last_used', sa.String(length=40), nullable=True),
    sa.ForeignKeyConstraint(
        ['key_id'], ['api_keys.key_id'],
        name=op.f('fk_api_key_usage_key_id_api_keys'),
        ondelete='CASCADE',
    ),
    sa.PrimaryKeyConstraint('key_id', name=op.f('pk_api_key_usage'))
    )

    op.create_table('review_tasks',
    sa.Column('task_id', sa.String(length=64), nullable=False),
    sa.Column('namespace', sa.String(length=64), nullable=False),
    sa.Column('file_id', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('queue_position', sa.Integer(), nullable=True),
    sa.Column('progress', sa.Float(), nullable=True),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('started_at', sa.Float(), nullable=True),
    sa.Column('completed_at', sa.Float(), nullable=True),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('webhook_url', sa.Text(), nullable=True),
    sa.Column('webhook_type', sa.String(length=20), nullable=True),
    sa.Column('priority', sa.Integer(), nullable=True),
    sa.Column('worker_id', sa.String(length=64), nullable=True),
    sa.PrimaryKeyConstraint('task_id', name=op.f('pk_review_tasks'))
    )
    with op.batch_alter_table('review_tasks', schema=None) as batch_op:
        batch_op.create_index(
            'idx_review_tasks_ns_status', ['namespace', 'status'], unique=False
        )
        batch_op.create_index('idx_review_tasks_created', ['created_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('review_tasks', schema=None) as batch_op:
        batch_op.drop_index('idx_review_tasks_created')
        batch_op.drop_index('idx_review_tasks_ns_status')
    op.drop_table('review_tasks')

    op.drop_table('api_key_usage')

    op.drop_table('api_keys')

    with op.batch_alter_table('rate_limit_buckets', schema=None) as batch_op:
        batch_op.drop_index('idx_rl_expires_at')
    op.drop_table('rate_limit_buckets')
