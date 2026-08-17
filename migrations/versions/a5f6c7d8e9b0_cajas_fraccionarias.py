"""Cantidades fraccionarias de caja: cajas y cajas_pedidas pasan a Float

Clientes piden fracciones de caja (media caja de atún Van Camps 160 g,
media de cooked shoulder 500 g). El form acepta múltiplos de 0.25 y las
columnas dejan de ser enteras. Los enteros existentes son floats válidos:
no hay remediación de datos.

En producción (Heroku Postgres) esto se aplica a mano, como siempre:

    heroku pg:psql --app pesosapp -c "ALTER TABLE detalle_pedido
        ALTER COLUMN cajas TYPE double precision,
        ALTER COLUMN cajas_pedidas TYPE double precision;"
    heroku restart --app pesosapp

Revision ID: a5f6c7d8e9b0
Revises: e1c2a3b4f5d6
Create Date: 2026-08-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a5f6c7d8e9b0'
down_revision = 'e1c2a3b4f5d6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('detalle_pedido') as batch_op:
        batch_op.alter_column(
            'cajas',
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            'cajas_pedidas',
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )


def downgrade():
    # Volver a Integer truncaría las fracciones (0.5 → 0); solo es seguro si
    # no se registraron pedidos fraccionarios todavía.
    with op.batch_alter_table('detalle_pedido') as batch_op:
        batch_op.alter_column(
            'cajas_pedidas',
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            'cajas',
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
