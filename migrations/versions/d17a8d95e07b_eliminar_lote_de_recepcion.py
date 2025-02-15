"""Eliminar columna fecha_expiracion de recepcion

Revision ID: d17a8d95e07b
Revises: e8897a04e926
Create Date: 2025-02-15 14:00:00

"""

# revision identifiers, used by Alembic.
revision = 'd17a8d95e07b'
down_revision = 'ca413cb75f80'
branch_labels = None
depends_on = None


from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

def upgrade():
    connection = op.get_bind()
    inspector = Inspector.from_engine(connection)
    table_names = inspector.get_table_names()
    if 'recepcion' in table_names:
        with op.batch_alter_table('recepcion') as batch_op:
            batch_op.drop_column('fecha_expiracion')
    else:
        # Si la tabla no existe, se omite esta migración
        print("La tabla 'recepcion' no existe. Se omite la eliminación de la columna 'fecha_expiracion'.")

def downgrade():
    # Para revertir el cambio, se vuelve a agregar la columna (ajusta el tipo de dato según tu modelo)
    with op.batch_alter_table('recepcion') as batch_op:
        batch_op.add_column(sa.Column('fecha_expiracion', sa.String(length=10), nullable=True))

