"""Add invoice_id_qbo to pedido

Revision ID: a1b2c3d4e5f6
Revises: c1b6a56753d6
Create Date: 2026-02-08 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'c1b6a56753d6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pedido',
        sa.Column('invoice_id_qbo', sa.String(100), nullable=True)
    )


def downgrade():
    op.drop_column('pedido', 'invoice_id_qbo')
