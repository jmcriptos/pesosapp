"""Add cajas_pedidas to detalle_pedido

Revision ID: e7f8a9b0c1d2
Revises: b16eb78bc4b5
Create Date: 2026-02-09 17:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f8a9b0c1d2'
down_revision = 'b16eb78bc4b5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('detalle_pedido',
                  sa.Column('cajas_pedidas', sa.Integer(),
                            nullable=False, server_default='0'))
    # Backfill: preserve original quantity from current cajas value
    op.execute("UPDATE detalle_pedido SET cajas_pedidas = cajas")


def downgrade():
    op.drop_column('detalle_pedido', 'cajas_pedidas')
