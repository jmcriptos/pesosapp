"""Rename estado listo to preparado

Revision ID: b16eb78bc4b5
Revises: d2e3f4a5b6c7
Create Date: 2026-02-09 00:35:30.983961

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b16eb78bc4b5'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE pedido SET estado = 'preparado' WHERE estado = 'listo'")


def downgrade():
    op.execute("UPDATE pedido SET estado = 'listo' WHERE estado = 'preparado'")
