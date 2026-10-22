"""producto.fabricado: fabricación propia (solo estos salen en etiquetas)

Boolean NOT NULL DEFAULT FALSE, precargado con la regla «se pesa o tiene
unidades por caja declaradas», que en producción (2026-10-21) separaba los
36 productos propios del atún, los aceites y los Underwood comprados.

En producción no hay release phase: va a mano ANTES del push.
    heroku pg:psql --app pesosapp -c "ALTER TABLE producto ADD COLUMN IF NOT EXISTS fabricado BOOLEAN NOT NULL DEFAULT FALSE; UPDATE producto SET fabricado = TRUE WHERE se_pesa OR unidades_por_caja IS NOT NULL;"

Revision ID: h4c5d6e7f8a9
Revises: g3b4c5d6e7f8
Create Date: 2026-10-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h4c5d6e7f8a9'
down_revision = 'g3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('producto')}
    if 'fabricado' not in cols:
        with op.batch_alter_table('producto', schema=None) as batch_op:
            batch_op.add_column(sa.Column('fabricado', sa.Boolean(), nullable=False,
                                          server_default=sa.false()))
        op.execute("UPDATE producto SET fabricado = TRUE WHERE se_pesa OR unidades_por_caja IS NOT NULL")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('producto')}
    if 'fabricado' in cols:
        with op.batch_alter_table('producto', schema=None) as batch_op:
            batch_op.drop_column('fabricado')
