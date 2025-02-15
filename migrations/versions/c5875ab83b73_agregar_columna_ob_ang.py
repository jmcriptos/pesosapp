"""Agregar columna ob_ang

Revision ID: c5875ab83b73
Revises: 8a24ec75021e
Create Date: 2024-09-28 14:53:20.560930
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = 'c5875ab83b73'
down_revision = '8a24ec75021e'
branch_labels = None
depends_on = None

def upgrade():
    connection = op.get_bind()
    inspector = Inspector.from_engine(connection)
    tables = inspector.get_table_names()
    if 'importacion' in tables:
        with op.batch_alter_table('importacion') as batch_op:
            batch_op.add_column(sa.Column('ob_ang', sa.Float(), nullable=True))
    else:
        # La tabla "importacion" no existe; se omite la operación
        print("La tabla 'importacion' no existe. Se omite la adición de la columna 'ob_ang'.")

def downgrade():
    connection = op.get_bind()
    inspector = Inspector.from_engine(connection)
    tables = inspector.get_table_names()
    if 'importacion' in tables:
        with op.batch_alter_table('importacion') as batch_op:
            batch_op.drop_column('ob_ang')
    else:
        print("La tabla 'importacion' no existe. Se omite la eliminación de la columna 'ob_ang'.")

