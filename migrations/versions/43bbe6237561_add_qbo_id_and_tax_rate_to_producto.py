"""Add tax_rate to producto (qbo_id already exists)

Revision ID: 43bbe6237561
Revises: 08181e47fe1e
Create Date: 2025-05-25 20:59:53.224759

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '43bbe6237561'
down_revision = '08181e47fe1e'
branch_labels = None
depends_on = None


def upgrade():
    # qbo_id ya existe en la tabla, lo omitimos
    # op.add_column('producto',
    #     sa.Column('qbo_id', sa.String(length=20), nullable=True, unique=True)
    # )

    # añadimos tax_rate con DEFAULT 0 para evitar violaciones de NOT NULL
    op.add_column('producto',
        sa.Column(
            'tax_rate',
            sa.Float(),
            nullable=False,
            server_default='0'
        )
    )
    # eliminamos el default en el esquema si no lo queremos permanentemente
    op.alter_column('producto', 'tax_rate', server_default=None)


def downgrade():
    # eliminamos sólo tax_rate
    op.drop_column('producto', 'tax_rate')
    # qbo_id no tocamos porque ya existía

