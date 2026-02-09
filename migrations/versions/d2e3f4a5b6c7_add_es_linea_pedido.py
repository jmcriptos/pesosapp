"""Add es_linea_pedido to detalle_pedido

Revision ID: d2e3f4a5b6c7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-08 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2e3f4a5b6c7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('detalle_pedido', sa.Column('es_linea_pedido', sa.Boolean(), nullable=False, server_default=sa.text('TRUE')))


def downgrade():
    op.drop_column('detalle_pedido', 'es_linea_pedido')
