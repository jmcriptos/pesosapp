"""add qbo_id to cliente and producto

Revision ID: fde620f42cae
Revises: ed70f8d30408
Create Date: 2025-05-25 15:01:58.422402

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fde620f42cae'
down_revision = 'ed70f8d30408'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None
    inspector = sa.inspect(bind)

    cliente_cols = {c['name'] for c in inspector.get_columns('cliente')}
    producto_cols = {c['name'] for c in inspector.get_columns('producto')}

    if 'qbo_id' not in cliente_cols:
        op.add_column('cliente', sa.Column('qbo_id', sa.String(length=20), nullable=True))
    if 'qbo_id' not in producto_cols:
        op.add_column('producto', sa.Column('qbo_id', sa.String(length=20), nullable=True))

    if dialect == 'sqlite':
        indexes = {idx['name'] for idx in inspector.get_indexes('cliente')}
        if 'ux_cliente_qbo_id' not in indexes:
            op.create_index('ux_cliente_qbo_id', 'cliente', ['qbo_id'], unique=True)

        indexes = {idx['name'] for idx in inspector.get_indexes('producto')}
        if 'ux_producto_qbo_id' not in indexes:
            op.create_index('ux_producto_qbo_id', 'producto', ['qbo_id'], unique=True)
    else:
        op.create_unique_constraint('ux_cliente_qbo_id', 'cliente', ['qbo_id'])
        op.create_unique_constraint('ux_producto_qbo_id', 'producto', ['qbo_id'])


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None

    if dialect == 'sqlite':
        op.drop_index('ux_producto_qbo_id', table_name='producto')
        op.drop_index('ux_cliente_qbo_id', table_name='cliente')
    else:
        op.drop_constraint('ux_producto_qbo_id', 'producto', type_='unique')
        op.drop_constraint('ux_cliente_qbo_id', 'cliente', type_='unique')

    op.drop_column('producto', 'qbo_id')
    op.drop_column('cliente', 'qbo_id')
