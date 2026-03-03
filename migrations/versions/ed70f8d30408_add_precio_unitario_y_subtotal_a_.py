"""add precio_unitario y subtotal a detalle_pedido

Revision ID: ed70f8d30408
Revises: a3dfe2d3a498
Create Date: 2025-05-25 14:26:49.879689
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ed70f8d30408'
down_revision = 'a3dfe2d3a498'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None

    if dialect == 'sqlite':
        inspector = sa.inspect(bind)
        cols = {c['name'] for c in inspector.get_columns('detalle_pedido')}

        if 'precio_unitario' not in cols:
            op.add_column(
                'detalle_pedido',
                sa.Column('precio_unitario', sa.Numeric(10, 2), nullable=False, server_default='0')
            )
        if 'subtotal' not in cols:
            op.add_column(
                'detalle_pedido',
                sa.Column('subtotal', sa.Numeric(10, 2), nullable=False, server_default='0')
            )
        return

    # --- cambios previos auto-generados ---
    op.alter_column(
        'cliente_lista_precio', 'fecha_asignacion',
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text('now()')
    )

    # Reconstrucción de FKs (sin ON DELETE) — se mantienen
    op.drop_constraint('cliente_lista_precio_lista_precio_id_fkey', 'cliente_lista_precio', type_='foreignkey')
    op.drop_constraint('cliente_lista_precio_cliente_id_fkey', 'cliente_lista_precio', type_='foreignkey')
    op.create_foreign_key(None, 'cliente_lista_precio', 'lista_precio', ['lista_precio_id'], ['id'])
    op.create_foreign_key(None, 'cliente_lista_precio', 'cliente',      ['cliente_id'],      ['id'])

    # --- NUEVOS CAMPOS EN detalle_pedido (opción A) ---
    op.add_column(
        'detalle_pedido',
        sa.Column('precio_unitario',
                  sa.Numeric(10, 2),
                  nullable=False,
                  server_default='0')
    )
    op.add_column(
        'detalle_pedido',
        sa.Column('subtotal',
                  sa.Numeric(10, 2),
                  nullable=False,
                  server_default='0')
    )

    # Resto de cambios auto-generados (fechas y FK-fixes)
    op.alter_column(
        'lista_precio', 'fecha_creacion',
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text('now()')
    )

    op.alter_column(
        'precio_cliente_producto', 'fecha_creacion',
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text('now()')
    )
    op.alter_column(
        'precio_cliente_producto', 'fecha_actualizacion',
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text('now()')
    )
    op.drop_constraint('precio_cliente_producto_cliente_id_fkey', 'precio_cliente_producto', type_='foreignkey')
    op.drop_constraint('precio_cliente_producto_producto_id_fkey', 'precio_cliente_producto', type_='foreignkey')
    op.create_foreign_key(None, 'precio_cliente_producto', 'cliente',  ['cliente_id'],  ['id'])
    op.create_foreign_key(None, 'precio_cliente_producto', 'producto', ['producto_id'], ['id'])

    op.alter_column(
        'precio_producto', 'fecha_actualizacion',
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text('now()')
    )
    op.drop_constraint('precio_producto_producto_id_fkey', 'precio_producto', type_='foreignkey')
    op.drop_constraint('precio_producto_lista_precio_id_fkey', 'precio_producto', type_='foreignkey')
    op.create_foreign_key(None, 'precio_producto', 'lista_precio', ['lista_precio_id'], ['id'])
    op.create_foreign_key(None, 'precio_producto', 'producto',     ['producto_id'],     ['id'])
    # --- fin upgrade ---


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None

    if dialect == 'sqlite':
        inspector = sa.inspect(bind)
        cols = {c['name'] for c in inspector.get_columns('detalle_pedido')}
        if 'subtotal' in cols:
            op.drop_column('detalle_pedido', 'subtotal')
        if 'precio_unitario' in cols:
            op.drop_column('detalle_pedido', 'precio_unitario')
        return

    # Deshacer los pasos en orden inverso

    op.drop_constraint(None, 'precio_producto', type_='foreignkey')
    op.drop_constraint(None, 'precio_producto', type_='foreignkey')
    op.create_foreign_key(
        'precio_producto_lista_precio_id_fkey',
        'precio_producto', 'lista_precio',
        ['lista_precio_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'precio_producto_producto_id_fkey',
        'precio_producto', 'producto',
        ['producto_id'], ['id'],
        ondelete='CASCADE'
    )
    op.alter_column(
        'precio_producto', 'fecha_actualizacion',
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text('now()')
    )

    op.drop_constraint(None, 'precio_cliente_producto', type_='foreignkey')
    op.drop_constraint(None, 'precio_cliente_producto', type_='foreignkey')
    op.create_foreign_key(
        'precio_cliente_producto_producto_id_fkey',
        'precio_cliente_producto', 'producto',
        ['producto_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'precio_cliente_producto_cliente_id_fkey',
        'precio_cliente_producto', 'cliente',
        ['cliente_id'], ['id'],
        ondelete='CASCADE'
    )
    op.alter_column(
        'precio_cliente_producto', 'fecha_actualizacion',
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text('now()')
    )
    op.alter_column(
        'precio_cliente_producto', 'fecha_creacion',
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text('now()')
    )

    op.alter_column(
        'lista_precio', 'fecha_creacion',
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text('now()')
    )

    # Eliminar las columnas recién añadidas
    op.drop_column('detalle_pedido', 'subtotal')
    op.drop_column('detalle_pedido', 'precio_unitario')

    op.drop_constraint(None, 'cliente_lista_precio', type_='foreignkey')
    op.drop_constraint(None, 'cliente_lista_precio', type_='foreignkey')
    op.create_foreign_key(
        'cliente_lista_precio_cliente_id_fkey',
        'cliente_lista_precio', 'cliente',
        ['cliente_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'cliente_lista_precio_lista_precio_id_fkey',
        'cliente_lista_precio', 'lista_precio',
        ['lista_precio_id'], ['id'],
        ondelete='CASCADE'
    )
    op.alter_column(
        'cliente_lista_precio', 'fecha_asignacion',
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text('now()')
    )
