"""Permitir valores NULL en lote, fecha_fabricacion y fecha_expiracion

Revision ID: 9b5b69d7a839
Revises: d8bda71c9188
Create Date: 2025-05-15 00:57:20.548971

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9b5b69d7a839'
down_revision = 'd8bda71c9188'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None

    if dialect == 'sqlite':
        with op.batch_alter_table('detalle_pedido', schema=None) as batch_op:
            batch_op.alter_column('lote', existing_type=sa.VARCHAR(length=50), nullable=True)
            batch_op.alter_column('fecha_fabricacion', existing_type=sa.VARCHAR(length=10), nullable=True)
            batch_op.alter_column('fecha_expiracion', existing_type=sa.VARCHAR(length=10), nullable=True)
    else:
        op.alter_column('detalle_pedido', 'lote', existing_type=sa.VARCHAR(length=50), nullable=True)
        op.alter_column('detalle_pedido', 'fecha_fabricacion', existing_type=sa.VARCHAR(length=10), nullable=True)
        op.alter_column('detalle_pedido', 'fecha_expiracion', existing_type=sa.VARCHAR(length=10), nullable=True)


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None

    if dialect == 'sqlite':
        with op.batch_alter_table('detalle_pedido', schema=None) as batch_op:
            batch_op.alter_column('fecha_expiracion', existing_type=sa.VARCHAR(length=10), nullable=False)
            batch_op.alter_column('fecha_fabricacion', existing_type=sa.VARCHAR(length=10), nullable=False)
            batch_op.alter_column('lote', existing_type=sa.VARCHAR(length=50), nullable=False)
    else:
        op.alter_column('detalle_pedido', 'fecha_expiracion', existing_type=sa.VARCHAR(length=10), nullable=False)
        op.alter_column('detalle_pedido', 'fecha_fabricacion', existing_type=sa.VARCHAR(length=10), nullable=False)
        op.alter_column('detalle_pedido', 'lote', existing_type=sa.VARCHAR(length=50), nullable=False)
