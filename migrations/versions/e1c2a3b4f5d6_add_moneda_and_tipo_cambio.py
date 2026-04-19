"""Add cliente.moneda + pedido.tipo_cambio (multi-currency support)

These columns were added to the models but never migrated. Production
was patched manually via heroku pg:psql, but any fresh dyno (replica,
staging, or a new clone) was missing them and would crash on the first
cliente fetch / pedido total. This formalizes them so:

- A new env can `flask db upgrade` to a working schema.
- The pytest suite (sqlite :memory: + create_all) keeps matching prod.

Revision ID: e1c2a3b4f5d6
Revises: d3f2e8b5a4c7
Create Date: 2026-04-19 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e1c2a3b4f5d6'
down_revision = 'd3f2e8b5a4c7'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    cliente_columns = {col['name'] for col in inspector.get_columns('cliente')}
    if 'moneda' not in cliente_columns:
        op.add_column(
            'cliente',
            sa.Column('moneda', sa.String(length=3), nullable=False, server_default='XCG'),
        )
        op.execute("UPDATE cliente SET moneda = 'XCG' WHERE moneda IS NULL")

    pedido_columns = {col['name'] for col in inspector.get_columns('pedido')}
    if 'tipo_cambio' not in pedido_columns:
        op.add_column(
            'pedido',
            sa.Column('tipo_cambio', sa.Float(), nullable=False, server_default='1.0'),
        )
        op.execute("UPDATE pedido SET tipo_cambio = 1.0 WHERE tipo_cambio IS NULL")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    pedido_columns = {col['name'] for col in inspector.get_columns('pedido')}
    if 'tipo_cambio' in pedido_columns:
        op.drop_column('pedido', 'tipo_cambio')

    cliente_columns = {col['name'] for col in inspector.get_columns('cliente')}
    if 'moneda' in cliente_columns:
        op.drop_column('cliente', 'moneda')
