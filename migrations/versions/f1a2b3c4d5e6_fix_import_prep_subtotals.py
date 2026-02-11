"""Fix import prep line subtotals (was stored as 0)

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-02-11 07:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    # Corregir subtotales de líneas de preparación de importación
    # que fueron auto-generadas con subtotal=0.
    # Fórmula correcta: subtotal = precio_unitario * cajas
    op.execute(
        """
        UPDATE detalle_pedido
        SET subtotal = ROUND(precio_unitario * cajas, 2)
        WHERE es_linea_pedido = false
          AND subtotal = 0
          AND cajas > 0
          AND precio_unitario > 0
        """
    )


def downgrade():
    # No revertimos porque el valor 0 era incorrecto
    pass
