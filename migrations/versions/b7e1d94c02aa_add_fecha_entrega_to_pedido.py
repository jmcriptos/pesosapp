"""Agregar campo fecha_entrega a tabla pedido

Lo necesita la pantalla "Repetir y ajustar" de /pedidos/nuevo: el vendedor
elige el día de entrega con chips (Hoy / Mañana / próximo día hábil / Otra) y
esa fecha tiene que ser consultable, no texto libre dentro de `notas`.

Es Date y no DateTime a propósito: se elige un día en ruta, nunca una hora.
Nullable porque los pedidos históricos no la tienen y no hay forma honesta de
inferirla — `fecha_pedido + N días` sería inventar dato.

Revision ID: b7e1d94c02aa
Revises: z99_add_performance_indexes
Create Date: 2026-08-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b7e1d94c02aa'
down_revision = 'z99_add_performance_indexes'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('pedido')}

    if 'fecha_entrega' not in cols:
        op.add_column(
            'pedido',
            sa.Column(
                'fecha_entrega',
                sa.Date(),
                nullable=True,
                comment='Día en que el cliente espera la entrega',
            ),
        )


def downgrade():
    op.drop_column('pedido', 'fecha_entrega')
