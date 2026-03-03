"""add proveedor column to producto

Revision ID: b7c8d9e0f1a3
Revises: f1a2b3c4d5e6
Create Date: 2026-03-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c8d9e0f1a3'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('producto')}

    if 'proveedor' not in cols:
        with op.batch_alter_table('producto', schema=None) as batch_op:
            batch_op.add_column(sa.Column('proveedor', sa.String(length=100), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('producto')}

    if 'proveedor' in cols:
        with op.batch_alter_table('producto', schema=None) as batch_op:
            batch_op.drop_column('proveedor')
