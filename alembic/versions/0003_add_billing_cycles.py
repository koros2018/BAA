"""add billing_cycles / billing_alerts tables (D4-T3)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('billing_cycles',
    sa.Column('cycle_id', sa.String(length=64), nullable=False),
    sa.Column('key_id', sa.String(length=64), nullable=False),
    sa.Column('start', sa.String(length=40), nullable=False),
    sa.Column('end', sa.String(length=40), nullable=False),
    sa.Column('review_count', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('rate', sa.Float(), nullable=False, server_default='0.0'),
    sa.Column('amount_due', sa.Float(), nullable=False, server_default='0.0'),
    sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
    sa.Column('paid_at', sa.String(length=40), nullable=True),
    sa.Column('payment_intent_id', sa.String(length=200), nullable=True),
    sa.PrimaryKeyConstraint('cycle_id'),
    sa.ForeignKeyConstraint(['key_id'], ['api_keys.key_id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_billing_cycles_key_id'), 'billing_cycles', ['key_id'], unique=False)

    op.create_table('billing_alerts',
    sa.Column('alert_id', sa.String(length=64), nullable=False),
    sa.Column('key_id', sa.String(length=64), nullable=False),
    sa.Column('cycle_id', sa.String(length=64), nullable=False),
    sa.Column('alert_type', sa.String(length=50), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('created_at', sa.String(length=40), nullable=False),
    sa.PrimaryKeyConstraint('alert_id'),
    )
    op.create_index(op.f('ix_billing_alerts_key_id'), 'billing_alerts', ['key_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_billing_alerts_key_id'), table_name='billing_alerts')
    op.drop_table('billing_alerts')
    op.drop_index(op.f('ix_billing_cycles_key_id'), table_name='billing_cycles')
    op.drop_table('billing_cycles')
