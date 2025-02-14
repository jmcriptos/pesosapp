"""Add fecha_registro to Facturacion

Revision ID: 724947d7525c
Revises: a8242fa1a2bf
Create Date: 2024-08-18 10:34:56.347784

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '724947d7525c'
down_revision = 'a8242fa1a2bf'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('facturacion', schema=None) as batch_op:
        # Añadir la columna con default=datetime.utcnow()
        batch_op.add_column(sa.Column('fecha_registro', sa.DateTime(), nullable=True))

    # Establecer la fecha de registro para registros existentes
    conn = op.get_bind()
    now = datetime.datetime.utcnow()
    conn.execute(
        sa.text(
            f"UPDATE facturacion SET fecha_registro = :now WHERE fecha_registro IS NULL"
        ),
        now=now
    )

    with op.batch_alter_table('facturacion', schema=None) as batch_op:
        # Ahora aplicar el NOT NULL
        batch_op.alter_column('fecha_registro',
                              existing_type=sa.DateTime(),
                              nullable=False)


def downgrade():
    with op.batch_alter_table('facturacion', schema=None) as batch_op:
        batch_op.drop_column('fecha_registro')


    # ### end Alembic commands ###
