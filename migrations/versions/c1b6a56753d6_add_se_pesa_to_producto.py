"""Add se_pesa to producto

Revision ID: c1b6a56753d6
Revises: f7a8b9c0d1e2, z99_add_performance_indexes
Create Date: 2026-02-08 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1b6a56753d6'
down_revision = ('f7a8b9c0d1e2', 'z99_add_performance_indexes')
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('producto', sa.Column('se_pesa', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')))


def downgrade():
    op.drop_column('producto', 'se_pesa')
