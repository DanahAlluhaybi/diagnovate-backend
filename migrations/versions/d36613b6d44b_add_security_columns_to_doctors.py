"""add security columns to doctors

Revision ID: d36613b6d44b
Revises:
Create Date: 2026-04-22 23:13:47.126050

"""
from alembic import op
import sqlalchemy as sa


revision = 'd36613b6d44b'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('doctors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('failed_attempts', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('locked_until', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('last_login', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('last_ip', sa.String(length=45), nullable=True))


def downgrade():
    with op.batch_alter_table('doctors', schema=None) as batch_op:
        batch_op.drop_column('last_ip')
        batch_op.drop_column('last_login')
        batch_op.drop_column('locked_until')
        batch_op.drop_column('failed_attempts')
