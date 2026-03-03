"""Agregar campo fecha_facturacion a tabla pedido

Revision ID: f7a8b9c0d1e2
Revises: 9d79cf425a74
Create Date: 2025-08-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f7a8b9c0d1e2'
down_revision = '9d79cf425a74'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('pedido')}

    # Agregar columna fecha_facturacion a la tabla pedido
    if 'fecha_facturacion' not in cols:
        op.add_column('pedido',
            sa.Column('fecha_facturacion',
                      sa.DateTime(),
                      nullable=True,
                      comment='Fecha y hora cuando el pedido fue facturado')
        )
    
    # Opcional: Actualizar pedidos existentes que están facturados
    # Les asignamos la fecha del pedido + 2 días como estimación
    if dialect == 'sqlite':
        op.execute("""
            UPDATE pedido
            SET fecha_facturacion = datetime(fecha_pedido, '+2 days')
            WHERE estado = 'facturado'
            AND fecha_facturacion IS NULL
        """)
    else:
        op.execute("""
            UPDATE pedido
            SET fecha_facturacion = fecha_pedido + INTERVAL '2 days'
            WHERE estado = 'facturado'
            AND fecha_facturacion IS NULL
        """)


def downgrade():
    # Eliminar la columna en caso de rollback
    op.drop_column('pedido', 'fecha_facturacion')
