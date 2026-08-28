"""etiquetas: unidades por caja y logo del cliente

Tres columnas nullable, sin datos que migrar:
  producto.unidades_por_caja  -> unidades que trae una caja (solo etiquetas)
  cliente.logo_etiqueta       -> bytes del logo del cliente (NULL = logo Jomar)
  cliente.logo_mimetype       -> 'image/png' | 'image/jpeg'

Revision ID: f2a3b4c5d6e7
Revises: a5f6c7d8e9b0
Create Date: 2026-08-27 20:43:13.557947

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2a3b4c5d6e7'
down_revision = 'a5f6c7d8e9b0'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    cols_producto = {c['name'] for c in inspector.get_columns('producto')}
    if 'unidades_por_caja' not in cols_producto:
        with op.batch_alter_table('producto', schema=None) as batch_op:
            batch_op.add_column(sa.Column('unidades_por_caja', sa.Integer(), nullable=True))

    cols_cliente = {c['name'] for c in inspector.get_columns('cliente')}
    with op.batch_alter_table('cliente', schema=None) as batch_op:
        if 'logo_etiqueta' not in cols_cliente:
            batch_op.add_column(sa.Column('logo_etiqueta', sa.LargeBinary(), nullable=True))
        if 'logo_mimetype' not in cols_cliente:
            batch_op.add_column(sa.Column('logo_mimetype', sa.String(length=50), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    cols_cliente = {c['name'] for c in inspector.get_columns('cliente')}
    with op.batch_alter_table('cliente', schema=None) as batch_op:
        if 'logo_mimetype' in cols_cliente:
            batch_op.drop_column('logo_mimetype')
        if 'logo_etiqueta' in cols_cliente:
            batch_op.drop_column('logo_etiqueta')

    cols_producto = {c['name'] for c in inspector.get_columns('producto')}
    if 'unidades_por_caja' in cols_producto:
        with op.batch_alter_table('producto', schema=None) as batch_op:
            batch_op.drop_column('unidades_por_caja')
