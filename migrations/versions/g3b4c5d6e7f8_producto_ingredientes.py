"""producto.ingredientes: listado para la etiqueta con ingredientes

Una columna Text nullable, sin datos que migrar. NULL = sin declarar.

En producción no hay release phase: el ALTER va a mano ANTES del push.
    heroku pg:psql --app pesosapp -c "ALTER TABLE producto ADD COLUMN IF NOT EXISTS ingredientes TEXT;"

Revision ID: g3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-10-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g3b4c5d6e7f8'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('producto')}
    if 'ingredientes' not in cols:
        with op.batch_alter_table('producto', schema=None) as batch_op:
            batch_op.add_column(sa.Column('ingredientes', sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('producto')}
    if 'ingredientes' in cols:
        with op.batch_alter_table('producto', schema=None) as batch_op:
            batch_op.drop_column('ingredientes')
